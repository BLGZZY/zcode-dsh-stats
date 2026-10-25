"""Install/remove an additive loader in the official app. No source build or DB writes.

ASAR pickle layout follows xhwxt/zcode-token-usage-statusbar (MIT); see vendor/LICENSE.
Existing payload bytes are preserved verbatim; only the main-entry record is replaced.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from host_platform import file_lock, default_asar

ROOT = Path(__file__).resolve().parent
ENTRY = 'out/main/index.js'
MARKER = re.compile(rb'\n/\* zcode-dsh-stats:start \*/.*?/\* zcode-dsh-stats:end \*/\n', re.S)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read_header(f):
    a, b, c, d = struct.unpack('<4I', f.read(16))
    if a != 4 or d > 64 * 1024 * 1024 or b != c + 4 or c < d + 4:
        raise ValueError('Unsupported ASAR header')
    return json.loads(f.read(d)), 8 + b


def node(header, name):
    for part in name.split('/'):
        header = header['files'][part]
    return header


def read_file(path, name):
    with Path(path).open('rb') as f:
        h, base = read_header(f)
        n = node(h, name)
        if n.get('unpacked') or 'link' in n:
            raise ValueError('Expected packed file')
        f.seek(base + int(n['offset']))
        result = f.read(n['size'])
        if len(result) != n['size']:
            raise ValueError('Truncated file')
        return result


def rewrite(src, dst, entry):
    with Path(src).open('rb') as f:
        h, base = read_header(f)
        n = node(h, ENTRY)
        n['offset'] = str(Path(src).stat().st_size - base)
        n['size'] = len(entry)
        block = 4194304
        n['integrity'] = {'algorithm': 'SHA256', 'hash': hashlib.sha256(entry).hexdigest(),
                          'blockSize': block, 'blocks': [hashlib.sha256(entry[i:i+block]).hexdigest() for i in range(0, len(entry), block)]}
        raw = json.dumps(h, ensure_ascii=False, separators=(',', ':')).encode()
        c = (len(raw) + 7) // 4 * 4
        with Path(dst).open('wb') as out:
            out.write(struct.pack('<4I', 4, c + 4, c, len(raw)))
            out.write(raw)
            out.write(b'\0' * (c - len(raw) - 4))
            f.seek(base)
            shutil.copyfileobj(f, out, 4 * 1024 * 1024)
            out.write(entry)
            out.flush()
            os.fsync(out.fileno())
    validate(src, dst, entry)


def validate(src, dst, entry):
    with Path(src).open('rb') as a, Path(dst).open('rb') as b:
        ha, ba = read_header(a); hb, bb = read_header(b)
        expected = copy.deepcopy(ha)
        expected['files']['out']['files']['main']['files']['index.js'] = node(hb, ENTRY)
        if expected != hb or read_file(dst, ENTRY) != entry:
            raise ValueError('ASAR validation failed')
        # All old payload bytes, including every other packed file, must survive unchanged.
        a.seek(ba); b.seek(bb)
        while chunk := a.read(4 * 1024 * 1024):
            if b.read(len(chunk)) != chunk:
                raise ValueError('Unexpected payload modification')


@contextmanager
def management_lock(runtime):
    """Serialize user enable, disable and removal decisions."""
    with file_lock(runtime / '.setup.lock', 'Another enable/disable/remove operation is running; try again later'):
        yield


@contextmanager
def install_lock(runtime):
    """Serialize manual, prepare, remove and automatic operations for this runtime."""
    with file_lock(runtime / 'install.lock', 'Another install/remove/prepare operation is running; try again later'):
        yield


def atomic_write(path, contents):
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(contents)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def sync_runtime(runtime):
    """Update only changed runtime files and preserve explicitly configured settings."""
    changed = []
    for name in ('collector.py', 'loader.cjs', 'overlay.js'):
        src, dst = ROOT / 'runtime' / name, runtime / name
        contents = src.read_bytes()
        if not dst.exists() or dst.read_bytes() != contents:
            atomic_write(dst, contents)
            changed.append(name)
    config_path = runtime / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError('Runtime config must be a JSON object; refusing to overwrite it')
    original = dict(config)
    config.setdefault('python', sys.executable)
    config.setdefault('database', str(Path.home() / '.zcode/cli/db/db.sqlite'))
    if not config_path.exists() or config != original:
        atomic_write(config_path, (json.dumps(config, indent=2) + '\n').encode())
        changed.append('config.json')
    return changed


def entry_change(asar, runtime, remove):
    """Validate identity and derive our entry addition without changing other loaders."""
    pkg = json.loads(read_file(asar, 'package.json'))
    if pkg.get('name') != '@zcode/desktop':
        raise ValueError('Target is not official ZCode desktop')
    old = read_file(asar, ENTRY)
    clean = MARKER.sub(b'', old)
    if remove:
        return pkg, old, clean
    if b'[zusage] load failed' in old:
        raise ValueError('Existing zusage overlay detected; remove its overlay first to avoid two bars')
    url = json.dumps((runtime / 'loader.cjs').as_uri())
    suffix = '\n/* zcode-dsh-stats:start */;import(' + url + ').catch(e=>console.error("[zcode-dsh-stats]",e.message));/* zcode-dsh-stats:end */\n'
    return pkg, old, clean + suffix.encode()


def verified_backup(asar, runtime, baseline):
    """One immutable, content-addressed backup per distinct installed archive."""
    backups = runtime / 'backups'
    backups.mkdir(exist_ok=True)
    backup = backups / (baseline + '-app.asar')
    if not backup.exists():
        fd, temp = tempfile.mkstemp(prefix='.backup-', suffix='.asar', dir=backups)
        os.close(fd)
        try:
            shutil.copy2(asar, temp)
            if sha(temp) != baseline:
                raise ValueError('Application changed while making backup; refusing overwrite')
            os.replace(temp, backup)
        finally:
            Path(temp).unlink(missing_ok=True)
    if sha(backup) != baseline:
        raise ValueError('Backup verification failed; refusing to replace existing backup')
    return backup


def auto_enabled(runtime):
    if (runtime / 'auto-disabled').exists():
        return False
    try:
        config = json.loads((runtime / 'auto.json').read_text())
        return isinstance(config, dict) and config.get('enabled') is True
    except (OSError, ValueError):
        return False


def install(asar, runtime, remove=False, prepare=False, *, automatic=False):
    asar, runtime = Path(asar).resolve(), Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    with management_lock(runtime) if remove else nullcontext():
        if remove:
            # Record opt-out even when an automatic install currently holds the install lock.
            atomic_write(runtime / 'auto-disabled', (datetime.now().isoformat() + '\n').encode())
        with install_lock(runtime):
            if automatic and not auto_enabled(runtime):
                return {'state': 'auto-disabled'}
            return install_locked(asar, runtime, remove, prepare, automatic)


def install_locked(asar, runtime, remove, prepare, automatic):
    baseline = sha(asar)
    pkg, old, modified = entry_change(asar, runtime, remove)
    if sha(asar) != baseline:
        raise ValueError('Application changed during inspection; refusing overwrite')
    # This path performs no archive write and creates no archive backup or receipt.
    if old == modified:
        changed = [] if remove else sync_runtime(runtime)
        return {'state': 'already-removed' if remove else 'already-installed',
                'version': pkg.get('version'), 'asar': str(asar), 'runtime': str(runtime),
                'runtimeUpdated': changed, 'restartRequired': bool(changed), 'sha256': baseline}
    backup = verified_backup(asar, runtime, baseline)
    # The verified snapshot is the only source for both metadata and payload rewriting.
    pkg, old, modified = entry_change(backup, runtime, remove)
    if not remove:
        sync_runtime(runtime)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    fd, temp = tempfile.mkstemp(prefix='.dsh-stats-', suffix='.asar', dir=runtime if prepare else asar.parent)
    os.close(fd)
    try:
        rewrite(backup, temp, modified)
        shutil.copymode(backup, temp)
        if sha(asar) != baseline:
            raise ValueError('Application changed during install; refusing overwrite')
        # Removal writes its opt-out before waiting for this lock, so an in-flight automatic restore also yields.
        if automatic and not auto_enabled(runtime):
            return {'state': 'auto-disabled'}
        if prepare:
            destination = runtime / 'prepared-app.asar'
        else:
            destination = asar
        os.replace(temp, destination)
    finally:
        Path(temp).unlink(missing_ok=True)
    record = {'state': 'prepared-not-installed' if prepare else 'removed' if remove else 'installed-restart-required', 'version': pkg.get('version'),
              'asar': str(asar), 'prepared': str(destination) if prepare else None,
              'backup': str(backup), 'beforeSha256': baseline, 'afterSha256': sha(destination),
              'runtime': str(runtime)}
    (runtime / (stamp + '-receipt.json')).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'remove', 'check', 'prepare'])
    parser.add_argument('--asar', type=Path)
    parser.add_argument('--runtime', type=Path, default=Path.home() / '.zcode-dsh-stats')
    args = parser.parse_args(argv)
    if args.asar is None:
        args.asar = default_asar()
    if args.action == 'check':
        print(json.dumps({'installed': bool(MARKER.search(read_file(args.asar, ENTRY))), 'sha256': sha(args.asar)}))
    else:
        if args.action == 'install':
            # Manual installs must use the same guard as setup and automatic repair.
            # Import here because compatibility uses this module's ASAR reader.
            from compatibility import check_target
            check_target(args.asar)
        print(json.dumps(install(args.asar, args.runtime.resolve(), args.action == 'remove', args.action == 'prepare'), indent=2))


if __name__ == '__main__':
    main()

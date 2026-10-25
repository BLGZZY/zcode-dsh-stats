"""One-time official plugin registration for update recovery; never edits host config by hand."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
import install as installer
from auto_restore import atomic_json, read_json
from compatibility import check_target
from host_platform import app_paths, default_asar

ROOT = Path(__file__).resolve().parent
PLUGIN_ID = 'zcode-dsh-stats@dsh-stats-local'


def stable_python():
    candidate = shutil.which('python3')
    if candidate and Path(candidate).resolve() == Path(sys.executable).resolve():
        return candidate
    return sys.executable


def build(runtime):
    market = runtime / 'auto-marketplace'
    plugin = market / 'plugins/zcode-dsh-stats'
    for name in ('install.py', 'auto_restore.py', 'compatibility.py', 'host_platform.py', 'windows_restore.py', 'hooks/session-start.py',
                 'runtime/loader.cjs', 'runtime/collector.py', 'runtime/overlay.js', 'LICENSE', 'vendor/LICENSE'):
        target = plugin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (plugin / '.zcode-plugin').mkdir(exist_ok=True)
    atomic_json(plugin / '.zcode-plugin/plugin.json', {
        'name': 'zcode-dsh-stats', 'version': '0.4.0',
        'description': '官方 ZCode 更新后自动恢复输入框底部 DSH 风格统计条。仅检查和恢复本组件，必要时下次正常重启生效。',
        'author': {'name': 'Local'}, 'license': 'MIT',
    })
    atomic_json(plugin / 'hooks/hooks.json', {'hooks': {'SessionStart': [{
        'matcher': 'startup|resume|clear|compact', 'hooks': [{
            'type': 'process', 'command': stable_python(),
            'args': ['${ZCODE_PLUGIN_ROOT}/hooks/session-start.py', '--runtime', str(runtime.resolve())],
            'timeoutMs': 60000, 'statusMessage': '检查 DSH 统计条更新恢复',
        }],
    }]}})
    atomic_json(market / 'marketplace.json', {
        'name': 'dsh-stats-local', 'owner': {'name': 'Local'},
        'plugins': [{'name': 'zcode-dsh-stats', 'source': './plugins/zcode-dsh-stats', 'version': '0.4.0'}],
    })
    return market, plugin


def cli(asar, args):
    paths = app_paths(asar)
    exe, bundle = paths['executable'], paths['cli']
    result = subprocess.run([str(exe), str(bundle), 'plugins', *args, '--json'],
                            env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'},
                            capture_output=True, text=True, encoding='utf-8', timeout=90)
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError('Official plugin CLI did not return JSON') from exc
    if result.returncode != 0 or data.get('ok') is False or data.get('success') is False:
        raise RuntimeError('Official plugin manager failed: ' + json.dumps(data, ensure_ascii=False)[:800])
    return data


@contextmanager
def setup_lock(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    with installer.management_lock(runtime):
        yield


def enable(asar, runtime):
    with setup_lock(runtime):
        return enable_locked(asar, runtime)


def enable_locked(asar, runtime):
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11+ is required')
    runtime.mkdir(parents=True, exist_ok=True)
    # Explicitly keep auto mode off until both initial installation and registration succeed.
    token = str(uuid.uuid4()).encode()
    installer.atomic_write(runtime / 'auto-disabled', token)
    compatibility = check_target(asar)
    market, plugin = build(runtime)
    cli(asar, ['validate', str(plugin)])
    installed = installer.install(asar, runtime)
    # Register using the shipped manager; do not rewrite installed_plugins/config manually.
    cli(asar, ['marketplace', 'add', str(market), '--scope', 'user'])
    cli(asar, ['install', PLUGIN_ID, '--scope', 'user'])
    cli(asar, ['enable', PLUGIN_ID, '--scope', 'user'])
    atomic_json(runtime / 'auto.json', {'enabled': True, 'asar': str(asar.resolve()), 'plugin': PLUGIN_ID})
    result = {'state': 'auto-restore-enabled', 'version': compatibility['version'],
              'component': installed['state'], 'plugin': PLUGIN_ID,
              'trigger': 'SessionStart', 'restartRequired': True}
    atomic_json(runtime / 'auto-setup-receipt.json', result)
    with installer.install_lock(runtime):
        if (runtime / 'auto-disabled').read_bytes() != token:
            raise RuntimeError('Setup cancelled by a concurrent removal; automatic restore stays disabled')
        (runtime / 'auto-disabled').unlink()
    return result


def disable(runtime):
    with setup_lock(runtime):
        installer.atomic_write(runtime / 'auto-disabled', b'disabled\n')
        # Do not report completion while an older repair can still replace the archive.
        with installer.install_lock(runtime):
            pass
    return {'state': 'auto-restore-disabled', 'componentRemoved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['enable', 'disable', 'status', 'build'])
    parser.add_argument('--asar', type=Path)
    parser.add_argument('--runtime', type=Path, default=Path.home() / '.zcode-dsh-stats')
    args = parser.parse_args()
    if args.action == 'enable' and args.asar is None:
        args.asar = default_asar()
    if args.action == 'enable':
        result = enable(args.asar, args.runtime)
    elif args.action == 'disable':
        result = disable(args.runtime)
    elif args.action == 'build':
        market, plugin = build(args.runtime)
        result = {'state': 'built-not-registered', 'marketplace': str(market), 'plugin': str(plugin)}
    else:
        cfg = read_json(args.runtime / 'auto.json')
        result = {'enabled': cfg.get('enabled') is True and not (args.runtime / 'auto-disabled').exists(),
                  'lastCheck': read_json(args.runtime / 'auto-status.json')}
    print(json.dumps(result, ensure_ascii=False, indent=2))

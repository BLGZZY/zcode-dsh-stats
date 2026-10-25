"""SessionStart restoration: bounded, opt-in, no model/network or session-data access."""
import fcntl
import json
import os
import struct
import time
from pathlib import Path
import install as installer
from compatibility import check_target

BACKOFF_SECONDS = 1800
DEFAULT_RUNTIME = Path.home() / '.zcode-dsh-stats'


def read_json(path):
    try:
        data = path.read_text()
    except FileNotFoundError:
        return {}
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError('Expected configuration object')
    return value


def atomic_json(path, data):
    temp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def identity(asar):
    s = asar.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]


def run(runtime=DEFAULT_RUNTIME, *, now=None, sleep=time.sleep):
    runtime = Path(runtime)
    if not runtime.exists() or (runtime / 'auto-disabled').exists():
        return {'state': 'disabled'}
    cfg = read_json(runtime / 'auto.json')
    if cfg.get('enabled') is not True:
        return {'state': 'disabled'}
    asar = Path(cfg['asar'])
    now = time.time() if now is None else now
    with (runtime / '.auto.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'state': 'busy'}
        status_file = runtime / 'auto-status.json'
        prior = read_json(status_file)
        observed = None
        try:
            observed = identity(asar)
            if prior.get('identity') == observed and prior.get('retryAfter', 0) > now:
                return {'state': 'backoff', 'reason': prior.get('reason'), 'retryAfter': prior['retryAfter']}
            entry = installer.read_file(asar, installer.ENTRY)
            url = json.dumps((runtime / 'loader.cjs').resolve().as_uri()).encode()
            if installer.MARKER.search(entry) and b';import(' + url + b')' in entry and all((runtime / n).is_file() for n in ('loader.cjs', 'overlay.js', 'collector.py')):
                result = {'state': 'installed', 'identity': observed, 'checkedAt': now}
            else:
                # Never rewrite an archive while an updater is still replacing it.
                if now - asar.stat().st_mtime < 5:
                    return {'state': 'update-in-progress'}
                sleep(0.25)
                if identity(asar) != observed:
                    return {'state': 'update-in-progress'}
                compatibility = check_target(asar)
                if identity(asar) != observed:
                    return {'state': 'update-in-progress'}
                if (runtime / 'auto-disabled').exists():
                    return {'state': 'disabled'}
                receipt = installer.install(asar, runtime, automatic=True)
                result = {'state': receipt['state'], 'version': compatibility['version'], 'identity': identity(asar), 'checkedAt': now}
            atomic_json(status_file, result)
            return result
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, struct.error) as exc:
            result = {'state': 'repair-failed', 'identity': observed, 'checkedAt': now,
                      'retryAfter': now + BACKOFF_SECONDS, 'reason': str(exc)[:350]}
            atomic_json(status_file, result)
            return result


def hook_output(result):
    out = {'suppressOutput': True}
    if result['state'] == 'installed-restart-required':
        out['systemMessage'] = 'DSH 统计组件已在 ZCode 更新后自动恢复。后台任务结束后，请完全退出并重新打开 ZCode 生效；不会自动中断任务。'
    elif result['state'] == 'repair-failed':
        out['systemMessage'] = 'DSH 统计组件自动恢复暂停：' + result.get('reason', 'unknown') + '。当前会话可继续；详情见 ~/.zcode-dsh-stats/auto-status.json。'
    if 'systemMessage' in out:
        # SessionStart consumes additionalContext, not systemMessage, in the shipped CLI.
        # Emit only this local maintenance notice; never pass through session input.
        out['hookSpecificOutput'] = {'hookEventName': 'SessionStart',
                                    'additionalContext': out['systemMessage']}
    return out


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))

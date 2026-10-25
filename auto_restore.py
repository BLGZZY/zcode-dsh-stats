"""SessionStart restoration: bounded, opt-in, no model/network or session-data access."""
import json
import os
import struct
import sys
import time
from pathlib import Path
from contextlib import ExitStack
from host_platform import file_lock, LockBusy
import install as installer
from compatibility import check_target

BACKOFF_SECONDS = 1800
DEFAULT_RUNTIME = Path.home() / '.zcode-dsh-stats'


def read_json(path):
    try:
        data = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return {}
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError('Expected configuration object')
    return value


def atomic_json(path, data):
    temp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def identity(asar):
    s = asar.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]


def run(runtime=DEFAULT_RUNTIME, *, now=None, sleep=time.sleep, defer=True):
    runtime = Path(runtime)
    if not runtime.exists() or (runtime / 'auto-disabled').exists():
        return {'state': 'disabled'}
    cfg = read_json(runtime / 'auto.json')
    if cfg.get('enabled') is not True:
        return {'state': 'disabled'}
    asar = Path(cfg['asar'])
    now = time.time() if now is None else now
    with ExitStack() as locks:
        try:
            locks.enter_context(file_lock(runtime / '.auto.lock', 'Automatic check already running'))
        except LockBusy:
            return {'state': 'busy'}
        status_file = runtime / 'auto-status.json'
        prior = read_json(status_file)
        observed = None
        install_attempt = False
        try:
            observed = identity(asar)
            if prior.get('identity') == observed and prior.get('retryAfter', 0) > now:
                return {'state': 'backoff', 'reason': prior.get('reason'), 'retryAfter': prior['retryAfter']}
            entry = installer.read_file(asar, installer.ENTRY)
            url = json.dumps((runtime / 'loader.cjs').resolve().as_uri()).encode()
            if installer.MARKER.search(entry) and b';import(' + url + b')' in entry and all((runtime / n).is_file() for n in ('loader.cjs', 'overlay.js', 'collector.py')):
                result = {'state': 'installed', 'identity': observed, 'checkedAt': now}
            else:
                if defer and sys.platform == 'win32' and prior.get('state') == 'deferred-until-exit' and prior.get('identity') == observed:
                    from windows_restore import is_app_running, queue_restore
                    if is_app_running(asar):
                        queued = queue_restore(asar, runtime)
                        result = {'state': 'deferred-until-exit', 'identity': observed,
                                  'checkedAt': now, **queued}
                        # Keep the state name stable even when a helper supplies diagnostics.
                        result['state'] = 'deferred-until-exit'
                        atomic_json(status_file, result)
                        return result
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
                install_attempt = True
                receipt = installer.install(asar, runtime, automatic=True)
                result = {'state': receipt['state'], 'version': compatibility['version'], 'identity': identity(asar), 'checkedAt': now}
            atomic_json(status_file, result)
            return result
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, struct.error) as exc:
            if isinstance(exc, PermissionError) and install_attempt and defer and sys.platform == 'win32':
                from windows_restore import is_app_running, queue_restore
                try:
                    if is_app_running(asar):
                        queued = queue_restore(asar, runtime)
                        result = {'state': 'deferred-until-exit', 'identity': observed,
                                  'checkedAt': now, **queued}
                        result['state'] = 'deferred-until-exit'
                        atomic_json(status_file, result)
                        return result
                except (OSError, RuntimeError) as worker_error:
                    exc = RuntimeError(f'{exc}; deferred recovery unavailable: {worker_error}')
            result = {'state': 'repair-failed', 'identity': observed, 'checkedAt': now,
                      'retryAfter': now + BACKOFF_SECONDS, 'reason': str(exc)[:350]}
            atomic_json(status_file, result)
            return result


def hook_output(result):
    out = {'suppressOutput': True}
    if result['state'] == 'installed-restart-required':
        out['systemMessage'] = 'DSH 统计组件已在 ZCode 更新后自动恢复。后台任务结束后，请完全退出并重新打开 ZCode 生效；不会自动中断任务。'
    elif result['state'] == 'deferred-until-exit':
        out['systemMessage'] = 'ZCode 正占用 Windows 应用文件。DSH 统计组件已安排在客户端正常退出后自动恢复，下次启动生效；请先完成当前任务，不会强制退出。'
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

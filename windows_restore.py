"""Wait for a specific Windows ZCode installation to exit, then repair once.

This bounded helper never stops an application, elevates privileges, or installs
a service. It always repairs the current archive through auto_restore's guards.
"""
import argparse
import ctypes
import json
import math
import ntpath
import os
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

from host_platform import LockBusy, app_paths, file_lock

POLL_SECONDS = 2.0
MAX_INSPECTION_FAILURES = 5


def _normalized_image(path):
    value = str(path)
    if value.startswith('\\\\?\\'):
        value = value[4:]
    return ntpath.normcase(ntpath.normpath(value))


def _windows_process_images(executable_name):
    """Read full image paths for matching process names, closing every handle.

    A same-name process whose path cannot be inspected is an error, not evidence
    that the target has exited. Processes that disappear during inspection are
    harmless; no permission or process state is changed.
    """
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    images = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            if entry.szExeFile.casefold() == executable_name.casefold():
                process = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not process:
                    error = ctypes.get_last_error()
                    if error != 87:  # ERROR_INVALID_PARAMETER: process exited.
                        raise ctypes.WinError(error)
                else:
                    try:
                        length = wintypes.DWORD(32768)
                        buffer = ctypes.create_unicode_buffer(length.value)
                        if kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
                            images.append(buffer.value)
                        else:
                            raise ctypes.WinError(ctypes.get_last_error())
                    finally:
                        kernel.CloseHandle(process)
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES is the normal enumeration terminator.
            raise ctypes.WinError(error)
    finally:
        kernel.CloseHandle(snapshot)
    return images


def is_app_running(asar):
    if sys.platform != 'win32':
        return False
    paths = app_paths(asar)
    if paths['platform'] != 'win32':
        raise ValueError('Windows restoration requires a Windows ZCode archive')
    executable = paths['executable'].resolve()
    expected = _normalized_image(executable)
    return any(_normalized_image(image) == expected
               for image in _windows_process_images(executable.name))


def queue_restore(asar, runtime):
    """Start a detached Python helper; its exclusive lock deduplicates workers."""
    if sys.platform != 'win32' or app_paths(asar)['platform'] != 'win32':
        raise RuntimeError('Deferred restoration is only available on Windows')
    runtime = Path(runtime).resolve()
    try:
        with file_lock(runtime / '.restore-worker.lock', 'Restore worker already running'):
            pass
    except LockBusy:
        try:
            status = json.loads((runtime / 'worker-status.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            status = {}
        if not isinstance(status, dict):
            raise ValueError('Expected restore worker status object')
        pid = status.get('workerPid')
        if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
            raise ValueError('Invalid restore worker process ID')
        return {'workerPid': pid, 'alreadyQueued': True}
    flags = (getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
             | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x00000200)
             | getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0x01000000))
    # A permitted breakaway lets the helper survive a short-lived caller's Job
    # (for example an SSH session). If its Job forbids this, Popen must fail;
    # never retry under another identity or report a worker that did not start.
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), '--runtime', str(runtime)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=flags, cwd=str(runtime),
    )
    return {'workerPid': child.pid}


def _configuration(runtime):
    if (runtime / 'auto-disabled').exists():
        return None
    try:
        cfg = json.loads((runtime / 'auto.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    if not isinstance(cfg, dict):
        raise ValueError('Expected automatic restoration configuration object')
    if cfg.get('enabled') is not True or (runtime / 'auto-disabled').exists():
        return None
    return cfg


def _write_status(runtime, result):
    fd, temp = tempfile.mkstemp(prefix='.restore-worker-', suffix='.tmp', dir=runtime)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temp, runtime / 'worker-status.json')
    finally:
        Path(temp).unlink(missing_ok=True)


def _failure(runtime, exc):
    result = {'state': 'worker-failed', 'workerPid': os.getpid(),
              'finishedAt': time.time(), 'reason': str(exc)[:350]}
    try:
        _write_status(runtime, result)
    except OSError as status_error:
        result['statusWriteError'] = type(status_error).__name__
    return result


def run_worker(runtime, timeout=24 * 3600, *, sleep=time.sleep, clock=time.monotonic):
    """Wait at most timeout seconds; retry only pre-install busy/updating states."""
    if sys.platform != 'win32':
        return {'state': 'unsupported-platform'}
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError('Worker timeout must be a finite nonnegative number')
    runtime = Path(runtime).resolve()
    if not runtime.exists():
        return {'state': 'disabled'}
    with ExitStack() as locks:
        try:
            locks.enter_context(file_lock(runtime / '.restore-worker.lock', 'Restore worker already running'))
        except LockBusy:
            return {'state': 'busy'}
        except OSError as exc:
            return _failure(runtime, exc)

        def finish(result):
            record = {**result, 'workerPid': os.getpid(), 'finishedAt': time.time()}
            _write_status(runtime, record)
            return record

        try:
            deadline = clock() + timeout
            target = None
            waiting_recorded = False
            inspection_failures = 0
            while True:
                # Opt-out takes precedence over process inspection and the timeout.
                cfg = _configuration(runtime)
                if cfg is None:
                    return finish({'state': 'disabled'})
                asar = Path(cfg['asar']).resolve()
                if app_paths(asar)['platform'] != 'win32':
                    raise ValueError('Configured restoration target is not a Windows app')
                if target is not None and asar != target:
                    return finish({'state': 'configuration-changed'})
                target = asar
                if clock() >= deadline:
                    return finish({'state': 'timed-out'})
                running = None
                try:
                    running = is_app_running(asar)
                    inspection_failures = 0
                except OSError as exc:
                    # Windows can deny image queries while a process is exiting.
                    # Retry only this read-only probe; never interpret failure as
                    # "exited", and never retry archive work through this path.
                    inspection_failures += 1
                    if inspection_failures >= MAX_INSPECTION_FAILURES:
                        raise
                    waiting_recorded = False
                    _write_status(runtime, {'state': 'waiting-for-process-inspection',
                                            'workerPid': os.getpid(), 'checkedAt': time.time(),
                                            'inspectionFailures': inspection_failures,
                                            'reason': str(exc)[:350]})
                if running is True:
                    if not waiting_recorded:
                        _write_status(runtime, {'state': 'waiting-for-app-exit',
                                                'workerPid': os.getpid(), 'startedAt': time.time()})
                        waiting_recorded = True
                elif running is False:
                    # Recheck after process enumeration; disabling must not schedule repair.
                    latest = _configuration(runtime)
                    if latest is None:
                        return finish({'state': 'disabled'})
                    if Path(latest['asar']).resolve() != target:
                        return finish({'state': 'configuration-changed'})
                    from auto_restore import run
                    result = run(runtime, defer=False)
                    if result.get('state') not in ('busy', 'update-in-progress'):
                        # In particular, do not retry repair-failed (which may already
                        # have prepared an ASAR), backoff, or any unexpected result.
                        return finish(result)
                remaining = deadline - clock()
                if remaining > 0:
                    sleep(min(POLL_SECONDS, remaining))
        except Exception as exc:
            return _failure(runtime, exc)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    result = run_worker(args.runtime)
    print(json.dumps(result, ensure_ascii=False))
    if result['state'] in ('worker-failed', 'repair-failed'):
        sys.exit(1)

"""Detached restoration contracts, without launching apps or waiting in real time."""
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auto_restore
import windows_restore as worker
from host_platform import LockBusy


class WindowsRestoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.runtime = Path(temporary.name).resolve()
        self.asar = self.runtime / 'ZCode/resources/app.asar'
        self.config = {'enabled': True, 'asar': str(self.asar)}
        self.write_config()
        self.now = 0

    def write_config(self):
        (self.runtime / 'auto.json').write_text(json.dumps(self.config), encoding='utf-8')

    def sleep(self, seconds):
        self.now += seconds

    @contextlib.contextmanager
    def mocked_host(self):
        with mock.patch.object(worker.sys, 'platform', 'win32'), \
                mock.patch.object(worker, 'file_lock', side_effect=lambda *args: contextlib.nullcontext()) as lock:
            yield lock

    def run_worker(self, timeout=20, sleep=None):
        return worker.run_worker(self.runtime, timeout, sleep=sleep or self.sleep, clock=lambda: self.now)

    def test_non_windows_does_not_inspect_processes_or_start_worker(self):
        with mock.patch.object(worker.sys, 'platform', 'darwin'), \
                mock.patch.object(worker, '_windows_process_images') as images, \
                mock.patch.object(worker.subprocess, 'Popen') as popen:
            self.assertFalse(worker.is_app_running(self.asar))
            self.assertEqual(self.run_worker()['state'], 'unsupported-platform')
            with self.assertRaisesRegex(RuntimeError, 'Windows'):
                worker.queue_restore(self.asar, self.runtime)
            images.assert_not_called()
            popen.assert_not_called()

    def test_process_detection_matches_full_path_not_just_name(self):
        expected = self.asar.parent.parent / 'ZCode.exe'
        with mock.patch.object(worker.sys, 'platform', 'win32'), \
                mock.patch.object(worker, '_windows_process_images', return_value=['C:\\Other\\ZCode.exe']) as images:
            self.assertFalse(worker.is_app_running(self.asar))
            images.assert_called_once_with('ZCode.exe')
            images.return_value = [str(expected).upper()]
            self.assertTrue(worker.is_app_running(self.asar))
            images.return_value = ['\\\\?\\' + str(expected)]
            self.assertTrue(worker.is_app_running(self.asar))

    def test_toolhelp_process_queries_close_snapshot_and_each_process_handle(self):
        entries = iter([(11, 'ZCode.exe'), (12, 'Other.exe'), (13, 'ZCODE.EXE')])
        error = {'code': 0}
        def next_process(snapshot, pointer):
            try:
                pid, name = next(entries)
            except StopIteration:
                error['code'] = 18
                return False
            pointer._obj.th32ProcessID = pid
            pointer._obj.szExeFile = name
            return True
        def query(process, flags, buffer, length):
            buffer.value = f'C:\\Install{process}\\ZCode.exe'
            return True
        kernel = mock.Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 90
        kernel.Process32FirstW.side_effect = next_process
        kernel.Process32NextW.side_effect = next_process
        kernel.OpenProcess.side_effect = lambda access, inherit, pid: pid + 100
        kernel.QueryFullProcessImageNameW.side_effect = query
        with mock.patch.object(worker.ctypes, 'WinDLL', return_value=kernel, create=True), \
                mock.patch.object(worker.ctypes, 'get_last_error', side_effect=lambda: error['code'], create=True):
            self.assertEqual(worker._windows_process_images('ZCode.exe'),
                             ['C:\\Install111\\ZCode.exe', 'C:\\Install113\\ZCode.exe'])
        self.assertEqual(kernel.OpenProcess.call_args_list,
                         [mock.call(0x1000, False, 11), mock.call(0x1000, False, 13)])
        self.assertEqual(kernel.CloseHandle.call_args_list,
                         [mock.call(111), mock.call(113), mock.call(90)])

    def test_toolhelp_query_failure_closes_handles_and_does_not_claim_exit(self):
        def first_process(snapshot, pointer):
            pointer._obj.th32ProcessID = 11
            pointer._obj.szExeFile = 'ZCode.exe'
            return True
        kernel = mock.Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 90
        kernel.Process32FirstW.side_effect = first_process
        kernel.OpenProcess.return_value = 111
        kernel.QueryFullProcessImageNameW.return_value = False
        with mock.patch.object(worker.ctypes, 'WinDLL', return_value=kernel, create=True), \
                mock.patch.object(worker.ctypes, 'get_last_error', return_value=5, create=True), \
                mock.patch.object(worker.ctypes, 'WinError', return_value=PermissionError('query denied'), create=True):
            with self.assertRaisesRegex(PermissionError, 'query denied'):
                worker._windows_process_images('ZCode.exe')
        self.assertEqual(kernel.CloseHandle.call_args_list, [mock.call(111), mock.call(90)])

    def test_queue_uses_detached_python_without_shell_or_inherited_streams(self):
        with self.mocked_host(), mock.patch.object(worker.subprocess, 'Popen', return_value=mock.Mock(pid=123)) as popen:
            self.assertEqual(worker.queue_restore(self.asar, self.runtime), {'workerPid': 123})
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [sys.executable, str(Path(worker.__file__).resolve()), '--runtime', str(self.runtime)])
        for stream in ('stdin', 'stdout', 'stderr'):
            self.assertEqual(kwargs[stream], subprocess.DEVNULL)
        self.assertEqual(kwargs['creationflags'], 0x8 | 0x200 | 0x01000000)
        self.assertTrue(kwargs['close_fds'])
        self.assertNotIn('shell', kwargs)

    def test_queue_rejected_breakaway_propagates_failure_without_fallback_or_pid(self):
        denied = PermissionError('Parent Job does not allow breakaway')
        with self.mocked_host(), mock.patch.object(worker.subprocess, 'Popen', side_effect=denied) as popen:
            with self.assertRaisesRegex(PermissionError, 'does not allow breakaway'):
                worker.queue_restore(self.asar, self.runtime)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(popen.call_args.kwargs['creationflags'], 0x8 | 0x200 | 0x01000000)
        self.assertFalse((self.runtime / 'worker-status.json').exists())

    def test_queue_existing_worker_returns_its_pid_without_spawning(self):
        (self.runtime / 'worker-status.json').write_text(
            json.dumps({'state': 'waiting-for-app-exit', 'workerPid': 4321,
                        'note': '等待客户端退出'}, ensure_ascii=False), encoding='utf-8')
        with self.mocked_host() as lock, mock.patch.object(worker.subprocess, 'Popen') as popen:
            lock.side_effect = LockBusy('worker running')
            self.assertEqual(worker.queue_restore(self.asar, self.runtime),
                             {'workerPid': 4321, 'alreadyQueued': True})
            popen.assert_not_called()
            self.assertEqual(lock.call_args.args[0], self.runtime / '.restore-worker.lock')

    def test_queue_busy_before_first_status_returns_unknown_pid_without_spawning(self):
        with self.mocked_host() as lock, mock.patch.object(worker.subprocess, 'Popen') as popen:
            lock.side_effect = LockBusy('worker starting')
            self.assertEqual(worker.queue_restore(self.asar, self.runtime),
                             {'workerPid': None, 'alreadyQueued': True})
            popen.assert_not_called()

    def test_queue_lock_permission_error_is_not_reported_as_queued(self):
        with self.mocked_host() as lock, mock.patch.object(worker.subprocess, 'Popen') as popen:
            lock.side_effect = PermissionError('worker lock denied')
            with self.assertRaisesRegex(PermissionError, 'worker lock denied'):
                worker.queue_restore(self.asar, self.runtime)
            popen.assert_not_called()

    def test_queue_probe_releases_lock_before_starting_child(self):
        held = []
        @contextlib.contextmanager
        def probe(*args):
            held.append(True)
            try:
                yield
            finally:
                held.pop()
        def spawn(*args, **kwargs):
            self.assertFalse(held)
            return mock.Mock(pid=123)
        with self.mocked_host() as lock, mock.patch.object(worker.subprocess, 'Popen', side_effect=spawn):
            lock.side_effect = probe
            self.assertEqual(worker.queue_restore(self.asar, self.runtime), {'workerPid': 123})

    def test_existing_worker_returns_busy_without_replacing_its_status(self):
        status = self.runtime / 'worker-status.json'
        status.write_text('{"state":"waiting-for-app-exit"}', encoding='utf-8')
        with self.mocked_host() as lock, mock.patch.object(auto_restore, 'run') as restore:
            lock.side_effect = LockBusy('busy')
            self.assertEqual(self.run_worker(), {'state': 'busy'})
            restore.assert_not_called()
        self.assertEqual(json.loads(status.read_text())['state'], 'waiting-for-app-exit')

    def test_worker_lock_permission_failure_is_recorded_not_mislabeled_busy(self):
        with self.mocked_host() as lock, mock.patch.object(auto_restore, 'run') as restore:
            lock.side_effect = PermissionError('lock denied')
            result = self.run_worker()
            self.assertEqual(result['state'], 'worker-failed')
            self.assertIn('lock denied', result['reason'])
            restore.assert_not_called()
        self.assertEqual(json.loads((self.runtime / 'worker-status.json').read_text())['state'], 'worker-failed')

    def test_waits_until_all_matching_processes_exit_then_repairs_once(self):
        with self.mocked_host() as lock, \
                mock.patch.object(worker, 'is_app_running', side_effect=[True, True, False]) as running, \
                mock.patch.object(auto_restore, 'run', return_value={'state': 'installed-restart-required'}) as restore:
            result = self.run_worker()
            self.assertEqual(result['state'], 'installed-restart-required')
            self.assertEqual(self.now, 4)
            self.assertEqual(running.call_count, 3)
            restore.assert_called_once_with(self.runtime, defer=False)
            self.assertEqual(lock.call_args.args[0], self.runtime / '.restore-worker.lock')
        self.assertEqual(json.loads((self.runtime / 'worker-status.json').read_text())['state'], result['state'])

    def test_disable_wins_before_process_inspection_and_timeout(self):
        (self.runtime / 'auto-disabled').write_bytes(b'disabled')
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running') as running, \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker(timeout=0)['state'], 'disabled')
            running.assert_not_called()
            restore.assert_not_called()

    def test_disable_while_waiting_never_repairs(self):
        def disable(seconds):
            self.sleep(seconds)
            (self.runtime / 'auto-disabled').write_bytes(b'disabled')
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', return_value=True), \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker(sleep=disable)['state'], 'disabled')
            restore.assert_not_called()

    def test_disable_during_process_inspection_is_rechecked(self):
        def stop_and_disable(asar):
            (self.runtime / 'auto-disabled').write_bytes(b'disabled')
            return False
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', side_effect=stop_and_disable), \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker()['state'], 'disabled')
            restore.assert_not_called()

    def test_configured_target_change_exits_without_repairing_either_copy(self):
        def change(seconds):
            self.sleep(seconds)
            self.config['asar'] = str(self.runtime / 'Other/resources/app.asar')
            self.write_config()
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', return_value=True), \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker(sleep=change)['state'], 'configuration-changed')
            restore.assert_not_called()

    def test_busy_and_update_in_progress_retry_without_assuming_app_stays_closed(self):
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', side_effect=[False, True, False, False]) as running, \
                mock.patch.object(auto_restore, 'run', side_effect=[{'state': 'busy'}, {'state': 'update-in-progress'}, {'state': 'installed'}]) as restore:
            self.assertEqual(self.run_worker()['state'], 'installed')
            self.assertEqual(restore.call_count, 3)
            self.assertEqual(running.call_count, 4)

    def test_repair_failure_and_backoff_are_terminal_without_repeated_asar_work(self):
        for state in ('repair-failed', 'backoff'):
            with self.subTest(state=state), self.mocked_host(), \
                    mock.patch.object(worker, 'is_app_running', return_value=False), \
                    mock.patch.object(auto_restore, 'run', return_value={'state': state, 'reason': '拒绝写入'}) as restore:
                self.assertEqual(self.run_worker()['state'], state)
                restore.assert_called_once()
                self.assertIn('拒绝写入', (self.runtime / 'worker-status.json').read_text(encoding='utf-8'))

    def test_timeout_is_bounded_and_does_not_repair_running_app(self):
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', return_value=True), \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker(timeout=3)['state'], 'timed-out')
            self.assertEqual(self.now, 3)
            restore.assert_not_called()

    def test_uninspectable_process_records_failure_instead_of_treating_app_as_closed(self):
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', side_effect=PermissionError('process query denied')) as running, \
                mock.patch.object(auto_restore, 'run') as restore:
            result = self.run_worker()
            self.assertEqual(result['state'], 'worker-failed')
            self.assertIn('process query denied', result['reason'])
            self.assertEqual(running.call_count, 5)
            self.assertEqual(self.now, 8)
            restore.assert_not_called()

    def test_transient_process_query_failure_waits_for_confirmed_exit(self):
        statuses = []
        def sleep(seconds):
            statuses.append(json.loads((self.runtime / 'worker-status.json').read_text(encoding='utf-8'))['state'])
            self.sleep(seconds)
        with self.mocked_host(), \
                mock.patch.object(worker, 'is_app_running', side_effect=[PermissionError('process exiting'), True, False]) as running, \
                mock.patch.object(auto_restore, 'run', return_value={'state': 'installed'}) as restore:
            self.assertEqual(self.run_worker(sleep=sleep)['state'], 'installed')
            self.assertEqual(running.call_count, 3)
            self.assertEqual(statuses, ['waiting-for-process-inspection', 'waiting-for-app-exit'])
            restore.assert_called_once_with(self.runtime, defer=False)

    def test_successful_process_probe_resets_consecutive_failure_budget(self):
        probes = [OSError('exiting')] * 4 + [True] + [OSError('exiting')] * 4 + [False]
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', side_effect=probes) as running, \
                mock.patch.object(auto_restore, 'run', return_value={'state': 'installed'}) as restore:
            self.assertEqual(self.run_worker(timeout=30)['state'], 'installed')
            self.assertEqual(running.call_count, 10)
            restore.assert_called_once_with(self.runtime, defer=False)

    def test_disable_and_timeout_still_take_priority_during_inspection_retries(self):
        def disable(seconds):
            self.sleep(seconds)
            (self.runtime / 'auto-disabled').write_bytes(b'disabled')
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', side_effect=OSError('exiting')) as running, \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker(sleep=disable)['state'], 'disabled')
            self.assertEqual(running.call_count, 1)
            restore.assert_not_called()
        (self.runtime / 'auto-disabled').unlink()
        self.now = 0
        with self.mocked_host(), mock.patch.object(worker, 'is_app_running', side_effect=OSError('exiting')) as running, \
                mock.patch.object(auto_restore, 'run') as restore:
            self.assertEqual(self.run_worker(timeout=3)['state'], 'timed-out')
            self.assertEqual(running.call_count, 2)
            self.assertEqual(self.now, 3)
            restore.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Real Windows process API smoke test')
    def test_real_windows_api_does_not_match_nonexistent_installation(self):
        self.assertFalse(worker.is_app_running(self.asar))


if __name__ == '__main__':
    unittest.main()

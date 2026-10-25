"""Host path selection and real POSIX / simulated Windows locking contracts."""
import errno
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_platform as host


class HostPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def create(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def windows_environment(self):
        return mock.patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'Local'),
                                            'ProgramFiles': str(self.root / 'Programs')}, clear=True)

    def test_app_layout_is_independent_of_host_os(self):
        mac = host.app_paths(self.root / 'ZCode.app/Contents/Resources/app.asar')
        self.assertEqual(mac['platform'], 'darwin')
        self.assertEqual(mac['executable'], self.root / 'ZCode.app/Contents/MacOS/ZCode')
        self.assertEqual(mac['cli'], self.root / 'ZCode.app/Contents/Resources/glm/zcode.cjs')
        self.assertEqual(mac['fuse_binary'], self.root / 'ZCode.app/Contents/Frameworks/Electron Framework.framework/Electron Framework')
        win = host.app_paths(self.root / 'ZCode/app-3.16.3/resources/app.asar')
        self.assertEqual(win['platform'], 'win32')
        self.assertEqual(win['executable'], self.root / 'ZCode/app-3.16.3/ZCode.exe')
        self.assertEqual(win['fuse_binary'], win['executable'])
        self.assertEqual(win['cli'], self.root / 'ZCode/app-3.16.3/resources/glm/zcode.cjs')

    def test_invalid_layout_does_not_guess_an_executable(self):
        with self.assertRaisesRegex(ValueError, '--asar'):
            host.app_paths(self.root / 'app.asar')

    def test_macos_default_is_unchanged(self):
        with mock.patch.object(host.sys, 'platform', 'darwin'):
            self.assertEqual(host.default_asar(), Path('/Applications/ZCode.app/Contents/Resources/app.asar'))

    def test_windows_missing_install_returns_usual_local_path(self):
        with self.windows_environment(), mock.patch.object(host.sys, 'platform', 'win32'):
            self.assertEqual(host.default_asar(), self.root / 'Local/Programs/ZCode/resources/app.asar')

    def test_windows_finds_program_files_and_squirrel_installations(self):
        for relative in ('Programs/ZCode/resources/app.asar', 'Local/ZCode/app-3.16.3/resources/app.asar'):
            with self.subTest(relative=relative):
                installed = self.create(relative)
                with self.windows_environment(), mock.patch.object(host.sys, 'platform', 'win32'):
                    self.assertEqual(host.default_asar(), installed)
                installed.unlink()

    def test_multiple_windows_copies_require_explicit_selection(self):
        self.create('Local/Programs/ZCode/resources/app.asar')
        self.create('Programs/ZCode/resources/app.asar')
        with self.windows_environment(), mock.patch.object(host.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(ValueError, '--asar'):
                host.default_asar()

    def test_duplicate_program_files_environment_does_not_create_ambiguity(self):
        installed = self.create('Programs/ZCode/resources/app.asar')
        with self.windows_environment(), mock.patch.dict(os.environ, {'ProgramW6432': str(self.root / 'Programs')}), \
                mock.patch.object(host.sys, 'platform', 'win32'):
            self.assertEqual(host.default_asar(), installed)


class LockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'operation.lock'

    @unittest.skipIf(sys.platform == 'win32', 'POSIX flock integration')
    def test_posix_contention_is_nonblocking_and_lock_releases_after_error(self):
        with self.assertRaisesRegex(ValueError, 'body failed'):
            with host.file_lock(self.path, 'busy'):
                with self.assertRaisesRegex(host.LockBusy, 'busy'):
                    with host.file_lock(self.path, 'busy'):
                        self.fail('Concurrent lock was granted')
                raise ValueError('body failed')
        with host.file_lock(self.path, 'busy') as stream:
            self.assertFalse(stream.closed)
        self.assertTrue(stream.closed)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_file_open_permission_error_is_not_busy(self):
        denied = PermissionError(errno.EACCES, 'permission denied')
        with mock.patch.object(host.os, 'open', side_effect=denied):
            with self.assertRaises(PermissionError):
                with host.file_lock(self.path, 'busy'):
                    self.fail('Opened a denied lock')

    def fake_windows(self, locking):
        return mock.patch.dict(sys.modules, {'msvcrt': types.SimpleNamespace(
            LK_NBLCK=2, LK_UNLCK=0, locking=locking)})

    def test_windows_locks_and_unlocks_byte_zero_even_if_body_moves_cursor(self):
        calls = []
        def locking(fd, mode, count):
            calls.append((mode, count, os.lseek(fd, 0, os.SEEK_CUR), os.fstat(fd).st_size))
        with mock.patch.object(host.sys, 'platform', 'win32'), self.fake_windows(locking):
            with host.file_lock(self.path, 'busy') as stream:
                stream.seek(8)
        self.assertEqual(calls, [(2, 1, 0, 1), (0, 1, 0, 1)])

    def test_windows_contention_does_not_unlock_failed_acquisition(self):
        locking = mock.Mock(side_effect=OSError(errno.EACCES, 'lock conflict'))
        with mock.patch.object(host.sys, 'platform', 'win32'), self.fake_windows(locking):
            with self.assertRaisesRegex(host.LockBusy, 'already running'):
                with host.file_lock(self.path, 'already running'):
                    self.fail('Conflicting lock granted')
        self.assertEqual(locking.call_count, 1)

    def test_windows_explicit_access_denied_is_not_reported_as_contention(self):
        denied = PermissionError(errno.EACCES, 'access denied')
        denied.winerror = 5
        locking = mock.Mock(side_effect=denied)
        with mock.patch.object(host.sys, 'platform', 'win32'), self.fake_windows(locking):
            with self.assertRaises(PermissionError):
                with host.file_lock(self.path, 'busy'):
                    self.fail('Denied lock granted')
        self.assertEqual(locking.call_count, 1)

    def test_windows_existing_contents_survive_and_body_error_releases_lock(self):
        self.path.write_bytes(b'existing')
        locking = mock.Mock()
        with mock.patch.object(host.sys, 'platform', 'win32'), self.fake_windows(locking):
            with self.assertRaisesRegex(ValueError, 'body failed'):
                with host.file_lock(self.path, 'busy') as stream:
                    stream.seek(4)
                    raise ValueError('body failed')
        self.assertEqual([call.args[1:] for call in locking.call_args_list], [(2, 1), (0, 1)])
        self.assertEqual(self.path.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()

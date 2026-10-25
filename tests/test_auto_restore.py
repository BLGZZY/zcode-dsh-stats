"""Automatic restoration never rewrites an updating or unsupported application."""
import contextlib
import hashlib
import io
import json
import os
import runpy
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import auto_restore as auto
import compatibility


def archive(path, *, main=b'official main', selectors=None, package=None):
    selectors = compatibility.SELECTORS if selectors is None else selectors
    package = package or {'name': '@zcode/desktop', 'version': 'test.2', 'main': 'out/main/index.js'}
    payloads = {
        'package.json': json.dumps(package).encode(),
        'out/main/index.js': main,
        'out/renderer/assets/index.js': b' '.join(sorted(selectors)),
    }
    header, data = {'files': {}}, b''
    for filename, content in payloads.items():
        branch = header
        parts = filename.split('/')
        for part in parts[:-1]:
            branch = branch['files'].setdefault(part, {'files': {}})
        branch['files'][parts[-1]] = {'size': len(content), 'offset': str(len(data))}
        data += content
    raw = json.dumps(header).encode()
    aligned = (len(raw) + 7) // 4 * 4
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<4I', 4, aligned + 4, aligned, len(raw)) + raw
                     + b'\0' * (aligned - len(raw) - 4) + data)


class AutoRestoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name).resolve()
        self.runtime = root / 'runtime'
        self.runtime.mkdir()
        self.asar = root / 'ZCode.app/Contents/Resources/app.asar'
        archive(self.asar)
        self.now = 2000
        os.utime(self.asar, (1000, 1000))
        self.sleep = mock.Mock()

    def enable(self):
        (self.runtime / 'auto.json').write_text(json.dumps({'enabled': True, 'asar': str(self.asar)}))

    def restore(self):
        return auto.run(self.runtime, now=self.now, sleep=self.sleep)

    def test_missing_config_and_non_true_values_are_disabled(self):
        with mock.patch.object(auto.installer, 'install') as install:
            self.assertEqual(self.restore(), {'state': 'disabled'})
            for enabled in (False, None, 'true', 1):
                (self.runtime / 'auto.json').write_text(json.dumps({'enabled': enabled}))
                self.assertEqual(self.restore(), {'state': 'disabled'})
            install.assert_not_called()

    def test_opt_out_marker_wins_over_explicit_enable(self):
        self.enable()
        (self.runtime / 'auto-disabled').touch()
        with mock.patch.object(auto.installer, 'install') as install:
            self.assertEqual(self.restore(), {'state': 'disabled'})
            install.assert_not_called()

    def test_present_matching_loader_is_fast_path_without_reinstall(self):
        self.enable()
        for name in ('loader.cjs', 'overlay.js', 'collector.py'):
            (self.runtime / name).write_text('runtime file')
        _, _, entry = auto.installer.entry_change(self.asar, self.runtime, False)
        archive(self.asar, main=entry)
        with mock.patch.object(auto.installer, 'install') as install, mock.patch.object(auto, 'check_target') as check:
            result = self.restore()
            self.assertEqual(result['state'], 'installed')
            install.assert_not_called()
            check.assert_not_called()
            self.sleep.assert_not_called()
            self.assertEqual(json.loads((self.runtime / 'auto-status.json').read_text())['state'], 'installed')

    def test_updated_archive_missing_marker_calls_opt_in_install_once(self):
        self.enable()
        with mock.patch.object(auto, 'check_target', return_value={'version': 'test.2'}) as check, \
             mock.patch.object(auto.installer, 'install', return_value={'state': 'installed-restart-required'}) as install:
            result = self.restore()
            self.assertEqual(result['state'], 'installed-restart-required')
            self.assertEqual(result['version'], 'test.2')
            check.assert_called_once_with(self.asar)
            install.assert_called_once_with(self.asar, self.runtime, automatic=True)
            self.sleep.assert_called_once_with(0.25)

    def test_recent_mtime_is_treated_as_update_in_progress(self):
        self.enable()
        os.utime(self.asar, (self.now - 2, self.now - 2))
        with mock.patch.object(auto.installer, 'install') as install, mock.patch.object(auto, 'check_target') as check:
            self.assertEqual(self.restore()['state'], 'update-in-progress')
            self.sleep.assert_not_called()
            install.assert_not_called()
            check.assert_not_called()

    def test_identity_change_during_settle_or_compatibility_defers_repair(self):
        self.enable()
        for identities in ([['old'], ['new']], [['old'], ['old'], ['new']]):
            with self.subTest(identities=identities), \
                 mock.patch.object(auto, 'identity', side_effect=identities), \
                 mock.patch.object(auto, 'check_target', return_value={'version': 'test.2'}), \
                 mock.patch.object(auto.installer, 'install') as install:
                self.assertEqual(self.restore()['state'], 'update-in-progress')
                install.assert_not_called()

    def test_same_identity_failure_backs_off_then_new_identity_retries(self):
        self.enable()
        with mock.patch.object(auto, 'identity', return_value=['version-a']), \
             mock.patch.object(auto, 'check_target', side_effect=ValueError('unsupported composer')) as check, \
             mock.patch.object(auto.installer, 'install') as install:
            failed = self.restore()
            self.assertEqual(failed['state'], 'repair-failed')
            self.assertEqual(failed['retryAfter'], self.now + 1800)
            self.assertEqual(self.restore()['state'], 'backoff')
            check.assert_called_once()
            install.assert_not_called()
        with mock.patch.object(auto, 'identity', return_value=['version-b']), \
             mock.patch.object(auto, 'check_target', return_value={'version': 'test.3'}), \
             mock.patch.object(auto.installer, 'install', return_value={'state': 'installed-restart-required'}) as install:
            self.assertEqual(self.restore()['state'], 'installed-restart-required')
            install.assert_called_once()

    def test_backoff_expires_at_thirty_minutes_for_same_identity(self):
        self.enable()
        (self.runtime / 'auto-status.json').write_text(json.dumps({
            'identity': ['same'], 'retryAfter': self.now, 'reason': 'old error'}))
        with mock.patch.object(auto, 'identity', return_value=['same']), \
             mock.patch.object(auto, 'check_target', return_value={'version': 'test.2'}), \
             mock.patch.object(auto.installer, 'install', return_value={'state': 'installed-restart-required'}) as install:
            self.assertEqual(self.restore()['state'], 'installed-restart-required')
            install.assert_called_once()

    def test_opt_out_during_compatibility_check_cancels_install(self):
        self.enable()
        def check(_):
            (self.runtime / 'auto-disabled').touch()
            return {'version': 'test.2'}
        with mock.patch.object(auto, 'check_target', side_effect=check), \
             mock.patch.object(auto.installer, 'install') as install:
            self.assertEqual(self.restore()['state'], 'disabled')
            install.assert_not_called()

    def test_permission_failure_in_installer_becomes_status_not_hook_failure(self):
        self.enable()
        original = self.asar.read_bytes()
        with mock.patch.object(auto, 'check_target', return_value={'version': 'test.2'}), \
             mock.patch.object(auto.installer, 'install', side_effect=PermissionError('read-only app')):
            result = self.restore()
        self.assertEqual(result['state'], 'repair-failed')
        self.assertEqual(self.asar.read_bytes(), original)
        output = auto.hook_output(result)
        self.assertTrue(output['suppressOutput'])
        self.assertIn('read-only app', output['systemMessage'])

    def test_hook_catches_early_permission_error_and_emits_only_valid_json(self):
        output = io.StringIO()
        with mock.patch.object(auto, 'run', side_effect=PermissionError('private path must not leak')), \
             contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT / 'hooks/session-start.py'), run_name='__main__')
        result = json.loads(output.getvalue())
        self.assertTrue(result['suppressOutput'])
        self.assertIn('PermissionError', result['systemMessage'])
        self.assertNotIn('private path', output.getvalue())
        self.assertNotIn('Traceback', output.getvalue())
        self.assertEqual(result['hookSpecificOutput'], {
            'hookEventName': 'SessionStart',
            'additionalContext': result['systemMessage'],
        })

    def test_truncated_archive_records_failure_and_backs_off_without_install(self):
        self.enable()
        self.asar.write_bytes(b'bad')
        os.utime(self.asar, (1000, 1000))
        with mock.patch.object(auto.installer, 'install') as install, mock.patch.object(auto, 'check_target') as check:
            failure = self.restore()
            self.assertEqual(failure['state'], 'repair-failed')
            self.assertEqual(failure['retryAfter'], self.now + 1800)
            stored = json.loads((self.runtime / 'auto-status.json').read_text())
            self.assertEqual(stored['state'], 'repair-failed')
            self.assertEqual(stored['identity'], auto.identity(self.asar))
            self.assertEqual(self.restore()['state'], 'backoff')
            install.assert_not_called()
            check.assert_not_called()
        self.assertEqual(self.asar.read_bytes(), b'bad')

    def test_repair_notifications_use_session_start_additional_context(self):
        for result in ({'state': 'installed-restart-required'},
                       {'state': 'repair-failed', 'reason': 'unsupported update'}):
            with self.subTest(result=result):
                output = auto.hook_output(result)
                self.assertTrue(output['suppressOutput'])
                self.assertEqual(output['hookSpecificOutput'], {
                    'hookEventName': 'SessionStart',
                    'additionalContext': output['systemMessage'],
                })
        for state in ('disabled', 'installed', 'backoff', 'busy', 'update-in-progress'):
            with self.subTest(state=state):
                self.assertEqual(auto.hook_output({'state': state}), {'suppressOutput': True})

    def test_hook_custom_runtime_passes_through_and_preserves_notification_envelope(self):
        output = io.StringIO()
        with mock.patch.object(auto, 'run', return_value={'state': 'installed-restart-required'}) as run, \
             mock.patch.object(sys, 'argv', ['session-start.py', '--runtime', str(self.runtime)]), \
             contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT / 'hooks/session-start.py'), run_name='__main__')
        run.assert_called_once_with(self.runtime)
        result = json.loads(output.getvalue())
        self.assertEqual(result['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertEqual(result['hookSpecificOutput']['additionalContext'], result['systemMessage'])


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.asar = root / 'ZCode.app/Contents/Resources/app.asar'
        self.binary = root / 'ZCode.app/Contents/Frameworks/Electron Framework.framework/Electron Framework'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'binary prefix' + compatibility.SENTINEL + bytes((1, 8)) + b'00000000' + b'tail')
        archive(self.asar)

    def test_compatible_target_is_checked_without_modification(self):
        original = {p: hashlib.sha256(p.read_bytes()).digest() for p in (self.asar, self.binary)}
        self.assertEqual(compatibility.check_target(self.asar), {'version': 'test.2', 'compatible': True})
        for path, digest in original.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)

    def test_enabled_integrity_fuse_refuses_without_changing_fuse_or_archive(self):
        self.binary.write_bytes(compatibility.SENTINEL + bytes((1, 8)) + b'00001000')
        before = (self.binary.read_bytes(), self.asar.read_bytes())
        with self.assertRaisesRegex(ValueError, 'integrity validation is enabled'):
            compatibility.check_target(self.asar)
        self.assertEqual((self.binary.read_bytes(), self.asar.read_bytes()), before)

    def test_unknown_missing_or_malformed_fuse_is_rejected(self):
        for binary in (b'no fuse', compatibility.SENTINEL + bytes((2, 8)) + b'00000000',
                       compatibility.SENTINEL + bytes((1, 8)) + b'0000x000',
                       compatibility.SENTINEL + bytes((1, 3)) + b'000'):
            with self.subTest(binary=binary):
                self.binary.write_bytes(binary)
                with self.assertRaises(ValueError):
                    compatibility.check_fuses(self.binary)
                self.assertEqual(self.binary.read_bytes(), binary)

    def test_missing_composer_selector_is_rejected_without_archive_write(self):
        archive(self.asar, selectors=compatibility.SELECTORS - {b'data-session-id'})
        original = self.asar.read_bytes()
        with self.assertRaisesRegex(ValueError, 'composer structure is not supported'):
            compatibility.check_target(self.asar)
        self.assertEqual(self.asar.read_bytes(), original)

    def test_missing_or_changed_main_entry_is_rejected_before_fuse_check(self):
        for main in (None, 'different/index.js'):
            with self.subTest(main=main):
                package = {'name': '@zcode/desktop', 'version': 'test.2'}
                if main is not None:
                    package['main'] = main
                archive(self.asar, package=package)
                original = self.asar.read_bytes()
                with mock.patch.object(compatibility, 'check_fuses') as fuses:
                    with self.assertRaisesRegex(ValueError, 'Unsupported ZCode package or entry point'):
                        compatibility.check_target(self.asar)
                    fuses.assert_not_called()
                self.assertEqual(self.asar.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()

"""One-time setup uses the official manager and enables recovery only after success."""
import contextlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import setup_auto as setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.runtime = self.root / 'custom runtime'
        self.asar = self.root / 'ZCode.app/Contents/Resources/app.asar'
        self.market = self.runtime / 'auto-marketplace'
        self.plugin = self.market / 'plugins/zcode-dsh-stats'

    def patched_enable(self):
        stack = self.enterContext(contextlib.ExitStack())
        check = stack.enter_context(mock.patch.object(setup, 'check_target', return_value={'version': '3.test'}))
        build = stack.enter_context(mock.patch.object(setup, 'build', return_value=(self.market, self.plugin)))
        cli = stack.enter_context(mock.patch.object(setup, 'cli', return_value={'success': True}))
        install = stack.enter_context(mock.patch.object(setup.installer, 'install', return_value={'state': 'installed-restart-required'}))
        return check, build, cli, install

    def test_registration_sequence_and_disabled_marker_until_every_step_succeeds(self):
        check, build, cli, install = self.patched_enable()
        events = []
        def checked(_):
            self.assertTrue((self.runtime / 'auto-disabled').exists())
            events.append('check')
            return {'version': '3.test'}
        def built(_):
            self.assertTrue((self.runtime / 'auto-disabled').exists())
            events.append('build')
            return self.market, self.plugin
        def registered(asar, args):
            self.assertEqual(asar, self.asar)
            self.assertTrue((self.runtime / 'auto-disabled').exists())
            events.append(tuple(args))
            return {'success': True}
        def installed(asar, runtime):
            self.assertEqual((asar, runtime), (self.asar, self.runtime))
            self.assertTrue((self.runtime / 'auto-disabled').exists())
            events.append('component')
            return {'state': 'installed-restart-required'}
        check.side_effect, build.side_effect = checked, built
        cli.side_effect, install.side_effect = registered, installed
        result = setup.enable(self.asar, self.runtime)
        self.assertEqual(events, [
            'check', 'build', ('validate', str(self.plugin)), 'component',
            ('marketplace', 'add', str(self.market), '--scope', 'user'),
            ('install', setup.PLUGIN_ID, '--scope', 'user'),
            ('enable', setup.PLUGIN_ID, '--scope', 'user'),
        ])
        self.assertEqual(result['state'], 'auto-restore-enabled')
        self.assertEqual(result['version'], '3.test')
        self.assertFalse((self.runtime / 'auto-disabled').exists())
        self.assertEqual(json.loads((self.runtime / 'auto.json').read_text()), {
            'enabled': True, 'asar': str(self.asar.resolve()), 'plugin': setup.PLUGIN_ID,
        })
        self.assertEqual(json.loads((self.runtime / 'auto-setup-receipt.json').read_text()), result)

    def test_each_pre_activation_failure_leaves_auto_disabled(self):
        cases = ('compatibility', 'build', 'validate', 'component', 'marketplace', 'install-plugin', 'enable-plugin', 'config')
        for stage in cases:
            with self.subTest(stage=stage):
                runtime = self.root / stage
                runtime.mkdir()
                # Re-enabling an already configured component must fail closed too.
                (runtime / 'auto.json').write_text(json.dumps({'enabled': True, 'asar': str(self.asar)}))
                real_atomic = setup.atomic_json
                def cli(_asar, args):
                    current = {'validate': 'validate', 'marketplace': 'marketplace',
                               'install': 'install-plugin', 'enable': 'enable-plugin'}[args[0]]
                    if stage == current:
                        raise RuntimeError(stage)
                    return {'success': True}
                def atomic(path, data):
                    if stage == 'config' and path.name == 'auto.json':
                        raise OSError('cannot persist configuration')
                    real_atomic(path, data)
                with mock.patch.object(setup, 'check_target', side_effect=RuntimeError(stage) if stage == 'compatibility' else None, return_value={'version': 'test'}), \
                     mock.patch.object(setup, 'build', side_effect=RuntimeError(stage) if stage == 'build' else None, return_value=(self.market, self.plugin)), \
                     mock.patch.object(setup, 'cli', side_effect=cli), \
                     mock.patch.object(setup.installer, 'install', side_effect=RuntimeError(stage) if stage == 'component' else None, return_value={'state': 'installed-restart-required'}), \
                     mock.patch.object(setup, 'atomic_json', side_effect=atomic):
                    with self.assertRaises((RuntimeError, OSError)):
                        setup.enable(self.asar, runtime)
                self.assertTrue((runtime / 'auto-disabled').exists())

    def test_receipt_write_failure_does_not_leave_auto_enabled(self):
        self.patched_enable()
        real_atomic = setup.atomic_json
        def atomic(path, data):
            if path.name == 'auto-setup-receipt.json':
                raise OSError('receipt filesystem unavailable')
            real_atomic(path, data)
        with mock.patch.object(setup, 'atomic_json', side_effect=atomic):
            with self.assertRaises(OSError):
                setup.enable(self.asar, self.runtime)
        self.assertTrue((self.runtime / 'auto-disabled').exists())

    def test_disable_preserves_installed_component_config_and_plugin_files(self):
        self.runtime.mkdir()
        files = {
            'loader.cjs': b'loader', 'overlay.js': b'overlay', 'collector.py': b'collector',
            'config.json': b'{"database":"existing"}',
            'auto.json': b'{"enabled":true}',
            'auto-marketplace/marketplace.json': b'{"name":"market"}',
        }
        for relative, content in files.items():
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        with mock.patch.object(setup, 'cli') as cli, mock.patch.object(setup.installer, 'install') as install:
            result = setup.disable(self.runtime)
            self.assertEqual(result, {'state': 'auto-restore-disabled', 'componentRemoved': False})
            self.assertTrue((self.runtime / 'auto-disabled').exists())
            for relative, content in files.items():
                self.assertEqual((self.runtime / relative).read_bytes(), content)
            cli.assert_not_called()
            install.assert_not_called()

    def test_disable_during_install_keeps_opt_out_but_does_not_report_completion(self):
        self.runtime.mkdir()
        component = self.runtime / 'overlay.js'
        component.write_bytes(b'active component')
        with setup.installer.install_lock(self.runtime):
            with self.assertRaisesRegex(RuntimeError, 'Another install/remove/prepare'):
                setup.disable(self.runtime)
            self.assertEqual((self.runtime / 'auto-disabled').read_bytes(), b'disabled\n')
            self.assertEqual(component.read_bytes(), b'active component')
        self.assertEqual(setup.disable(self.runtime)['state'], 'auto-restore-disabled')

    def test_remove_during_enable_is_rejected_without_cleanup_or_token_change(self):
        actual_install = setup.installer.install
        self.runtime.mkdir()
        component = self.runtime / 'overlay.js'
        component.write_bytes(b'component remains installed')
        self.asar.parent.mkdir(parents=True)
        self.asar.write_bytes(b'official archive must not be opened')
        _, _, cli, _ = self.patched_enable()
        attempts = []
        def registered(_asar, args):
            if args[0] == 'validate':
                token = (self.runtime / 'auto-disabled').read_bytes()
                with self.assertRaisesRegex(RuntimeError, 'Another enable/disable/remove'):
                    actual_install(self.asar, self.runtime, remove=True)
                self.assertEqual((self.runtime / 'auto-disabled').read_bytes(), token)
                self.assertEqual(component.read_bytes(), b'component remains installed')
                self.assertEqual(self.asar.read_bytes(), b'official archive must not be opened')
                self.assertFalse((self.runtime / 'backups').exists())
                attempts.append('rejected')
            return {'ok': True}
        cli.side_effect = registered
        self.assertEqual(setup.enable(self.asar, self.runtime)['state'], 'auto-restore-enabled')
        self.assertEqual(attempts, ['rejected'])

    def test_enable_does_not_clear_a_replaced_cancellation_token(self):
        _, _, cli, _ = self.patched_enable()
        def registered(_asar, args):
            if args[0] == 'enable':
                (self.runtime / 'auto-disabled').write_bytes(b'external opt out')
            return {'ok': True}
        cli.side_effect = registered
        with self.assertRaisesRegex(RuntimeError, 'Setup cancelled'):
            setup.enable(self.asar, self.runtime)
        self.assertEqual((self.runtime / 'auto-disabled').read_bytes(), b'external opt out')

    def test_build_is_self_contained_and_hook_passes_custom_runtime_as_argument(self):
        with mock.patch.object(setup, 'stable_python', return_value='/stable path/python3'), \
             mock.patch.object(setup, 'cli') as cli, mock.patch.object(setup.installer, 'install') as install, \
             mock.patch.object(setup, 'check_target') as check:
            market, plugin = setup.build(self.runtime)
        self.assertEqual(market, self.market)
        self.assertEqual(plugin, self.plugin)
        required = ('install.py', 'auto_restore.py', 'compatibility.py', 'host_platform.py', 'windows_restore.py', 'hooks/session-start.py',
                    'runtime/loader.cjs', 'runtime/collector.py', 'runtime/overlay.js', 'LICENSE', 'vendor/LICENSE')
        for relative in required:
            path = plugin / relative
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), (ROOT / relative).read_bytes())
        manifest = json.loads((plugin / '.zcode-plugin/plugin.json').read_text())
        self.assertEqual(manifest['name'], 'zcode-dsh-stats')
        market_manifest = json.loads((market / 'marketplace.json').read_text())
        self.assertEqual(market_manifest['plugins'][0]['source'], './plugins/zcode-dsh-stats')
        hook_group = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']['SessionStart'][0]
        self.assertEqual(hook_group['matcher'], 'startup|resume|clear|compact')
        hook = hook_group['hooks'][0]
        self.assertEqual(hook['type'], 'process')
        self.assertEqual(hook['command'], '/stable path/python3')
        self.assertEqual(hook['args'], ['${ZCODE_PLUGIN_ROOT}/hooks/session-start.py', '--runtime', str(self.runtime.resolve())])
        self.assertEqual(hook['timeoutMs'], 60000)
        self.assertFalse((self.runtime / 'auto.json').exists())
        cli.assert_not_called(); install.assert_not_called(); check.assert_not_called()
        # Import from the copied distribution in an isolated Python process. No hook is run.
        code = 'import sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root)); import auto_restore,install,compatibility,host_platform,windows_restore; assert all(Path(m.__file__).parent==root for m in (auto_restore,install,compatibility,host_platform,windows_restore))'
        completed = subprocess.run([sys.executable, '-I', '-c', code, str(plugin)],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_cli_uses_shipped_official_binary_with_json_and_no_shell(self):
        reply = subprocess.CompletedProcess([], 0, stdout='{"ok":true}', stderr='')
        with mock.patch.object(setup.subprocess, 'run', return_value=reply) as run:
            self.assertEqual(setup.cli(self.asar, ['enable', setup.PLUGIN_ID]), {'ok': True})
        args, kwargs = run.call_args
        self.assertEqual(args[0], [str(self.asar.parent.parent / 'MacOS/ZCode'),
                                   str(self.asar.parent / 'glm/zcode.cjs'), 'plugins',
                                   'enable', setup.PLUGIN_ID, '--json'])
        self.assertEqual(kwargs['env']['ELECTRON_RUN_AS_NODE'], '1')
        self.assertEqual(kwargs['timeout'], 90)
        self.assertNotIn('shell', kwargs)

    def test_cli_rejects_non_json_failure_exit_and_negative_envelopes(self):
        for code, stdout in ((0, 'not json'), (1, '{"ok":true}'),
                             (0, '{"ok":false}'), (0, '{"success":false}')):
            with self.subTest(code=code, stdout=stdout), \
                 mock.patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, stdout=stdout, stderr='')):
                with self.assertRaises(RuntimeError):
                    setup.cli(self.asar, ['validate', 'unused'])

    def test_windows_cli_uses_exe_and_shipped_cli_as_separate_arguments(self):
        asar = self.root / 'Windows ZCode/resources/app.asar'
        executable = asar.parent.parent / 'ZCode.exe'
        bundle = asar.parent / 'glm/zcode.cjs'
        for path in (asar, executable, bundle):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        reply = subprocess.CompletedProcess([], 0, stdout='{"ok":true}', stderr='')
        with mock.patch.object(setup.subprocess, 'run', return_value=reply) as run:
            self.assertEqual(setup.cli(asar, ['validate', str(self.plugin)]), {'ok': True})
        args, kwargs = run.call_args
        self.assertEqual(args[0], [str(executable), str(bundle), 'plugins',
                                  'validate', str(self.plugin), '--json'])
        self.assertEqual(kwargs['env']['ELECTRON_RUN_AS_NODE'], '1')
        self.assertFalse(kwargs.get('shell', False))


if __name__ == '__main__':
    unittest.main()

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1] / 'install.py')
mod = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mod)


def fixture(root):
    src = root / 'app.asar'
    main = b'console.log("official");\nimport("other-plugin.cjs");'
    pkg = b'{"name":"@zcode/desktop","version":"test"}'
    data = b'untouched binary\x00\xff'
    h = {'files': {'package.json': {'size': len(pkg), 'offset': '0'},
         'out': {'files': {'main': {'files': {'index.js': {'size': len(main), 'offset': str(len(pkg))}}}}},
         'asset.bin': {'size': len(data), 'offset': str(len(pkg)+len(main))}}}
    raw = json.dumps(h).encode(); c = (len(raw)+7)//4*4
    src.write_bytes(struct.pack('<4I',4,c+4,c,len(raw))+raw+b'\0'*(c-len(raw)-4)+pkg+main+data)
    return src, root / 'runtime', main, data


class InstallerTest(unittest.TestCase):
    def test_roundtrip_preserves_unrelated_file_and_other_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'app.asar'; runtime = root / 'runtime'
            main = b'console.log("official");\nimport("other-plugin.cjs");'
            pkg = b'{"name":"@zcode/desktop","version":"test"}'
            data = b'untouched binary\x00\xff'
            h = {'files': {'package.json': {'size': len(pkg), 'offset': '0'},
                 'out': {'files': {'main': {'files': {'index.js': {'size': len(main), 'offset': str(len(pkg))}}}}},
                 'asset.bin': {'size': len(data), 'offset': str(len(pkg)+len(main))}}}
            raw = json.dumps(h).encode(); c = (len(raw)+7)//4*4
            src.write_bytes(struct.pack('<4I',4,c+4,c,len(raw))+raw+b'\0'*(c-len(raw)-4)+pkg+main+data)
            original = src.read_bytes()
            prepared = mod.install(src, runtime, prepare=True)
            self.assertEqual(prepared['state'], 'prepared-not-installed')
            self.assertEqual(src.read_bytes(), original)
            self.assertIn(b'zcode-dsh-stats:start', mod.read_file(prepared['prepared'], mod.ENTRY))
            self.assertEqual(mod.read_file(prepared['prepared'], 'asset.bin'), data)
            receipt = mod.install(src, runtime)
            self.assertEqual(Path(receipt['backup']).read_bytes(), original)
            self.assertEqual(mod.read_file(src,'asset.bin'),data)
            self.assertIn(main,mod.read_file(src,mod.ENTRY))
            mod.install(src,runtime)
            self.assertEqual(len(mod.MARKER.findall(mod.read_file(src,mod.ENTRY))),1)
            mod.install(src,runtime,True)
            self.assertEqual(mod.read_file(src,mod.ENTRY),main)
            self.assertEqual(mod.read_file(src,'asset.bin'),data)

    def test_repeated_install_does_not_grow_archive_or_make_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            mod.install(src, runtime)
            installed = src.read_bytes()
            backups = sorted(p.name for p in (runtime / 'backups').iterdir())
            receipts = sorted(p.name for p in runtime.glob('*-receipt.json'))
            for _ in range(3):
                result = mod.install(src, runtime)
                self.assertEqual(result['state'], 'already-installed')
                self.assertFalse(result['restartRequired'])
            self.assertEqual(src.read_bytes(), installed)
            self.assertEqual(sorted(p.name for p in (runtime / 'backups').iterdir()), backups)
            self.assertEqual(sorted(p.name for p in runtime.glob('*-receipt.json')), receipts)
            # Repair a runtime asset without touching the archive again.
            (runtime / 'overlay.js').write_text('broken local copy')
            repaired = mod.install(src, runtime)
            self.assertEqual(repaired['runtimeUpdated'], ['overlay.js'])
            self.assertTrue(repaired['restartRequired'])
            self.assertEqual(src.read_bytes(), installed)

    def test_prepare_and_install_reuse_verified_content_addressed_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            baseline = mod.sha(src)
            first = mod.install(src, runtime, prepare=True)
            second = mod.install(src, runtime, prepare=True)
            third = mod.install(src, runtime)
            self.assertEqual(first['backup'], second['backup'])
            self.assertEqual(second['backup'], third['backup'])
            self.assertEqual(Path(first['backup']).name, baseline + '-app.asar')
            self.assertEqual(len(list((runtime / 'backups').glob('*.asar'))), 1)
            self.assertEqual(mod.sha(first['backup']), baseline)

    def test_existing_runtime_config_preserves_database_python_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            runtime.mkdir()
            config = {'database': '/custom/db.sqlite', 'python': '/custom/python', 'future': {'key': True}}
            (runtime / 'config.json').write_text(json.dumps(config))
            mod.install(src, runtime)
            mod.install(src, runtime)
            self.assertEqual(json.loads((runtime / 'config.json').read_text()), config)

    def test_remove_disables_auto_even_when_nothing_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            original = src.read_bytes()
            result = mod.install(src, runtime, remove=True)
            self.assertEqual(result['state'], 'already-removed')
            self.assertTrue((runtime / 'auto-disabled').exists())
            self.assertEqual(src.read_bytes(), original)
            self.assertFalse((runtime / 'backups').exists())

    def test_concurrent_operation_fails_clearly_and_remove_still_records_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            runtime.mkdir()
            with mod.install_lock(runtime):
                with self.assertRaisesRegex(RuntimeError, 'Another install/remove/prepare'):
                    mod.install(src, runtime)
                with self.assertRaisesRegex(RuntimeError, 'Another install/remove/prepare'):
                    mod.install(src, runtime, remove=True)
                self.assertTrue((runtime / 'auto-disabled').exists())

    def test_target_change_during_rewrite_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            original = src.read_bytes()
            upgraded = original[:-1] + b'X'
            rewrite = mod.rewrite

            def concurrent_upgrade(snapshot, destination, entry):
                self.assertNotEqual(Path(snapshot), src)
                self.assertEqual(Path(snapshot).read_bytes(), original)
                rewrite(snapshot, destination, entry)
                src.write_bytes(upgraded)

            with mock.patch.object(mod, 'rewrite', side_effect=concurrent_upgrade):
                with self.assertRaisesRegex(ValueError, 'Application changed during install'):
                    mod.install(src, runtime)
            self.assertEqual(src.read_bytes(), upgraded)

    def test_auto_install_requires_explicit_enable_and_respects_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            original = src.read_bytes()
            self.assertEqual(mod.install(src, runtime, automatic=True)['state'], 'auto-disabled')
            self.assertEqual(src.read_bytes(), original)
            (runtime / 'auto.json').write_text(json.dumps({'enabled': True}))
            (runtime / 'auto-disabled').touch()
            self.assertEqual(mod.install(src, runtime, automatic=True)['state'], 'auto-disabled')
            self.assertEqual(src.read_bytes(), original)
            (runtime / 'auto-disabled').unlink()
            self.assertEqual(mod.install(src, runtime, automatic=True)['state'], 'installed-restart-required')

    def test_opt_out_during_auto_rewrite_prevents_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, runtime, _, _ = fixture(Path(tmp))
            original = src.read_bytes()
            runtime.mkdir()
            (runtime / 'auto.json').write_text(json.dumps({'enabled': True}))
            rewrite = mod.rewrite

            def removal_requested(snapshot, destination, entry):
                rewrite(snapshot, destination, entry)
                (runtime / 'auto-disabled').touch()

            with mock.patch.object(mod, 'rewrite', side_effect=removal_requested):
                result = mod.install(src, runtime, automatic=True)
            self.assertEqual(result['state'], 'auto-disabled')
            self.assertEqual(src.read_bytes(), original)


if __name__ == '__main__': unittest.main()

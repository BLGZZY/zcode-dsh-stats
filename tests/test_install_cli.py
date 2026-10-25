"""Manual CLI installs reject incompatible apps without blocking cleanup."""
import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import install as installer
import compatibility


class InstallCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.asar = self.root / 'app.asar'
        self.runtime = self.root / 'runtime'

    def invoke(self, action):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            installer.main([action, '--asar', str(self.asar), '--runtime', str(self.runtime)])
        return json.loads(output.getvalue())

    def test_rejected_compatibility_never_calls_install_or_creates_runtime(self):
        self.asar.write_bytes(b'unsupported application')
        with mock.patch.object(compatibility, 'check_target', side_effect=ValueError('integrity enabled')) as check, \
                mock.patch.object(installer, 'install') as install:
            with self.assertRaisesRegex(ValueError, 'integrity enabled'):
                self.invoke('install')
            check.assert_called_once_with(self.asar)
            install.assert_not_called()
        self.assertEqual(self.asar.read_bytes(), b'unsupported application')
        self.assertFalse(self.runtime.exists())

    def test_compatible_install_checks_target_before_installing(self):
        order = []
        with mock.patch.object(compatibility, 'check_target', side_effect=lambda path: order.append('check')) as check, \
                mock.patch.object(installer, 'install', side_effect=lambda *args: order.append('install') or {'state': 'installed-restart-required'}) as install:
            self.assertEqual(self.invoke('install')['state'], 'installed-restart-required')
            self.assertEqual(order, ['check', 'install'])
            check.assert_called_once_with(self.asar)
            install.assert_called_once_with(self.asar, self.runtime, False, False)

    def test_remove_cleans_loader_even_when_target_is_no_longer_compatible(self):
        main = b'console.log("official");'
        package = b'{"name":"@zcode/desktop","version":"test"}'
        header = {'files': {
            'package.json': {'size': len(package), 'offset': '0'},
            'out': {'files': {'main': {'files': {'index.js': {'size': len(main), 'offset': str(len(package))}}}}},
        }}
        raw = json.dumps(header).encode()
        aligned = (len(raw) + 7) // 4 * 4
        self.asar.write_bytes(struct.pack('<4I', 4, aligned + 4, aligned, len(raw))
                              + raw + b'\0' * (aligned - len(raw) - 4) + package + main)
        installer.install(self.asar, self.runtime)
        self.assertTrue(installer.MARKER.search(installer.read_file(self.asar, installer.ENTRY)))
        with mock.patch.object(compatibility, 'check_target', side_effect=ValueError('unsupported new version')) as check:
            self.assertEqual(self.invoke('remove')['state'], 'removed')
            check.assert_not_called()
        self.assertEqual(installer.read_file(self.asar, installer.ENTRY), main)
        self.assertTrue((self.runtime / 'auto-disabled').exists())

    def test_prepare_remains_available_without_compatibility_check(self):
        with mock.patch.object(compatibility, 'check_target', side_effect=ValueError('unsupported new version')) as check, \
                mock.patch.object(installer, 'install', return_value={'state': 'prepared-not-installed'}) as install:
            self.assertEqual(self.invoke('prepare')['state'], 'prepared-not-installed')
            check.assert_not_called()
            install.assert_called_once_with(self.asar, self.runtime, False, True)


if __name__ == '__main__':
    unittest.main()

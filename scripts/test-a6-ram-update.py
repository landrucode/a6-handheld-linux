#!/usr/bin/env python3
"""Exercise signed bundle rejection and atomic selection with a disposable key."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('updater', Path(__file__).with_name('manage-a6-ram-update.py'))
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_root, self.old_public = updater.ROOT, updater.PUBLIC
        updater.ROOT = self.root
        (self.root / 'build').mkdir()
        self.key = self.root / 'key.pem'
        updater.PUBLIC = self.root / 'public.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True)
        subprocess.run(['openssl', 'pkey', '-in', str(self.key), '-pubout', '-out', str(updater.PUBLIC)], check=True)

    def tearDown(self):
        updater.ROOT, updater.PUBLIC = self.old_root, self.old_public
        self.tmp.cleanup()

    def sign(self, bundle, source, signature):
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.key),
                        '-in', str(bundle / source), '-out', str(bundle / signature)], check=True)

    def release(self, bundle):
        data = dict(format=1, files={name: updater.digest(bundle / name) for name in updater.FILES})
        (bundle / 'release.json').write_text(json.dumps(data))
        self.sign(bundle, 'release.json', 'release.sig')

    def bundle(self, name):
        bundle = self.root / 'build' / name
        bundle.mkdir()
        for filename in updater.FILES:
            (bundle / filename).write_text(name + filename)
        metadata = dict(image_sha256=updater.digest(bundle / 'a6-wifi.img3'),
                        sha256=updater.digest(bundle / 'modules.tar.gz'),
                        hardening=True, boot_defaults=True)
        (bundle / 'manifest.json').write_text(json.dumps(metadata))
        (bundle / 'manifest.sha256').write_text(''.join(
            updater.digest(bundle / filename) + '  ' + filename + '\n'
            for filename in ('a6-wifi.img3', 'a6-desktop.squashfs')))
        self.sign(bundle, 'manifest.sha256', 'manifest.sig')
        self.release(bundle)
        return bundle

    def test_apply_and_retained_previous(self):
        a, b = self.bundle('a'), self.bundle('b')
        updater.apply(a)
        pointer = self.root / 'build/ram-updates/selection.json'
        first = json.loads(pointer.read_text())['current']
        updater.apply(b)
        second = json.loads(pointer.read_text())
        self.assertEqual(second['previous'], first)
        updater.verify(self.root / first)
        updater.apply(b)
        self.assertEqual(json.loads(pointer.read_text()), second)

    def test_tampered_module_does_not_change_selection(self):
        a, b = self.bundle('a'), self.bundle('b')
        updater.apply(a)
        pointer = self.root / 'build/ram-updates/selection.json'
        before = pointer.read_bytes()
        (b / 'modules.tar.gz').write_text('tampered')
        with self.assertRaises(ValueError):
            updater.apply(b)
        self.assertEqual(pointer.read_bytes(), before)

    def test_bad_signature_rejected(self):
        bundle = self.bundle('a')
        (bundle / 'release.sig').write_bytes(b'broken')
        with self.assertRaises(subprocess.CalledProcessError):
            updater.verify(bundle)

    def test_copy_corruption_does_not_change_selection(self):
        a, b = self.bundle('a'), self.bundle('b')
        updater.apply(a)
        pointer = self.root / 'build/ram-updates/selection.json'
        before = pointer.read_bytes()
        copy = updater.shutil.copyfile

        def corrupt(source, destination):
            result = copy(source, destination)
            if Path(destination).name == 'modules.tar.gz':
                Path(destination).write_text('copy corrupted')
            return result

        with patch.object(updater.shutil, 'copyfile', corrupt), self.assertRaises(ValueError):
            updater.apply(b)
        self.assertEqual(pointer.read_bytes(), before)

    def test_signed_auxiliary_runtime(self):
        bundle = self.bundle('browser')
        for name in updater.AUXILIARY:
            (bundle / name).write_bytes(b'runtime')
        data = dict(format=2, files={name: updater.digest(bundle / name)
                                    for name in (*updater.FILES, *updater.AUXILIARY)})
        (bundle / 'release.json').write_text(json.dumps(data))
        self.sign(bundle, 'release.json', 'release.sig')
        updater.apply(bundle)
        pointer = self.root / 'build/ram-updates/selection.json'
        before = pointer.read_bytes()
        (bundle / 'browser.squashfs').write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            updater.apply(bundle)
        self.assertEqual(pointer.read_bytes(), before)

    def test_signed_app_helpers_reject_tampering(self):
        bundle = self.bundle('apps')
        for name in (*updater.AUXILIARY, 'app-helpers.tar.gz'):
            (bundle / name).write_bytes(b'public runtime')
        data = dict(format=3, files={name: updater.digest(bundle / name)
                                    for name in (*updater.FILES, *updater.AUXILIARY, 'app-helpers.tar.gz')})
        (bundle / 'release.json').write_text(json.dumps(data))
        self.sign(bundle, 'release.json', 'release.sig')
        updater.apply(bundle)
        pointer = self.root / 'build/ram-updates/selection.json'
        before = pointer.read_bytes()
        (bundle / 'app-helpers.tar.gz').write_bytes(b'tampered helper')
        with self.assertRaises(ValueError):
            updater.apply(bundle)
        self.assertEqual(pointer.read_bytes(), before)

    def test_symlink_rejected(self):
        bundle = self.bundle('a')
        (bundle / 'modules.tar.gz').unlink()
        (bundle / 'modules.tar.gz').symlink_to(bundle / 'a6-wifi.img3')
        with self.assertRaises(ValueError):
            updater.verify(bundle)

    def test_signed_wrong_metadata_rejected(self):
        bundle = self.bundle('a')
        data = json.loads((bundle / 'manifest.json').read_text())
        data['image_sha256'] = '0' * 64
        (bundle / 'manifest.json').write_text(json.dumps(data))
        self.release(bundle)
        with self.assertRaises(ValueError):
            updater.verify(bundle)


if __name__ == '__main__':
    unittest.main()

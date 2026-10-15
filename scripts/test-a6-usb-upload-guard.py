#!/usr/bin/env python3
"""Exercise the actual image guard with fake network tools in an isolated tree."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Guard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tmp').mkdir()
        usb = self.root / 'sys/class/net/usb0'
        (usb / 'statistics').mkdir(parents=True)
        for name in ('carrier', 'operstate', 'statistics/rx_packets', 'statistics/tx_packets',
                     'statistics/rx_errors', 'statistics/tx_errors'):
            (usb / name).write_text('1\n')
        script = (ROOT / 'rootfs/a6-usb-upload-recover.sh').read_text()
        script = script.replace('/tmp/', str(self.root / 'tmp') + '/')
        script = script.replace('/sys/class/net/', str(self.root / 'sys/class/net') + '/')
        self.script = self.root / 'guard.sh'
        self.script.write_text(script)
        fake = self.root / 'busybox'
        fake.write_text('#!/bin/sh\ncase "$1" in\n'
                        'netstat) test ! -e "$GUARD_TEST_ROOT/listener" || echo "LISTEN :8083 "; exit 0;;\n'
                        'grep) shift; exec /usr/bin/grep "$@";;\n'
                        'date) shift; exec /usr/bin/date "$@";;\n'
                        'ip) echo "$*" >> "$GUARD_TEST_ROOT/actions"; exit 0;;\n'
                        '*) exit 99;;\nesac\n')
        fake.chmod(0o700)
        self.env = dict(os.environ, PATH=str(self.root) + ':' + os.environ['PATH'],
                        GUARD_TEST_ROOT=str(self.root))

    def run_guard(self):
        return subprocess.run(['sh', str(self.script)], env=self.env, capture_output=True)

    def test_explicit_retries_cycle_only_ethernet(self):
        expected = ['ip link set usb0 down', 'ip link set usb0 up', 'ip link show usb0']
        for attempt in range(2):
            result = self.run_guard()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.root / 'actions').read_text().splitlines(), expected * (attempt + 1))
        self.assertEqual(len(list((self.root / 'tmp').glob('a6-usb-upload-recovery-*.before'))), 2)
        self.assertFalse((self.root / 'tmp/a6-usb-upload-recovery.lock').exists())

    def test_concurrent_recovery_refused(self):
        (self.root / 'tmp/a6-usb-upload-recovery.lock').mkdir()
        self.assertNotEqual(self.run_guard().returncode, 0)
        self.assertFalse((self.root / 'actions').exists())

    def test_startup_refused(self):
        (self.root / 'tmp/a6-wifi-boot.ready').touch()
        self.assertNotEqual(self.run_guard().returncode, 0)
        self.assertFalse((self.root / 'actions').exists())

    def test_wlan_refused(self):
        (self.root / 'sys/class/net/wlan0').mkdir()
        self.assertNotEqual(self.run_guard().returncode, 0)
        self.assertFalse((self.root / 'actions').exists())

    def test_active_receiver_refused(self):
        (self.root / 'listener').touch()
        self.assertNotEqual(self.run_guard().returncode, 0)
        self.assertFalse((self.root / 'actions').exists())


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Collect the passive WLAN clock snapshot over ACM; no clock/radio writes."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('uperf_3f101084', 'usbreg_3f10109c', 'ehci_3f10108c',
          'phy1_3f1002a4', 'ehci_secondary_3f1002a8', 'usb_ctl_3f108000')


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = ROOT / 'build/session-logs' / (stamp + '-wifi-clock-' + secrets.token_hex(4))
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = 'A6_WIFI_CLOCK_CAPTURE_' + secrets.token_hex(8)
    command = ('cat /sys/firmware/a6_wifi_clock_snapshot/status && '
               'dmesg | busybox grep A6_WIFI_CLOCK_SNAPSHOT_V1; echo ' + marker)
    console = prefix.with_suffix('.console.txt')
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'),
             command, '--until', marker, '--timeout', '20'],
            text=True, capture_output=True, timeout=30, check=False)
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
        console.write_text(text(exc.stdout) + text(exc.stderr))
        raise RuntimeError(f'ACM capture timed out; partial evidence: {console}') from exc
    console.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'ACM capture failed; partial evidence: {console}')
    lines = result.stdout.replace('\r', '').splitlines()
    snapshots = [line for line in lines
                 if line.startswith('A6_WIFI_CLOCK_SNAPSHOT_V1 frozen=1 writes=0 uperf_3f101084=')]
    if len(snapshots) != 1:
        raise RuntimeError(f'missing or ambiguous sysfs snapshot: {console}')
    values = dict(re.findall(r'(\w+)=([0-9a-f]{8})(?:\s|$)', snapshots[0]))
    if set(values) != set(FIELDS):
        raise RuntimeError(f'unexpected snapshot fields: {console}')
    report = {
        'captured_at_utc': stamp,
        'frozen_boot_snapshot': True,
        'register_writes': 0,
        'radio_enabled_by_capture': False,
        'values': values,
        'console_sha256': hashlib.sha256(console.read_bytes()).hexdigest(),
        'console': str(console.relative_to(ROOT)),
    }
    path = prefix.with_suffix('.json')
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Saved passive clock snapshot: {path}')
    for field in FIELDS:
        print(f'{field}={values[field]}')


if __name__ == '__main__':
    main()

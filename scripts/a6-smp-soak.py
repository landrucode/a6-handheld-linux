#!/usr/bin/env python3
"""Start or preserve the RAM-only representative desktop soak over USB ACM."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('power', ROOT / 'scripts/a6-phone-power-log.py')
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=('start', 'collect'))
p.add_argument('--desktop-pid', type=int)
a = p.parse_args()
if a.action == 'start':
    if a.desktop_pid is None or a.desktop_pid <= 1:
        p.error('start requires --desktop-pid for the verified Hyprland process')
    blob = (ROOT / 'rootfs/a6-smp-soak.sh').read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    encoded = base64.b64encode(blob).decode()
    power.serial(': > /tmp/a6-smp-soak.b64; echo A6_SOAK_CLEAR', 'A6_SOAK_CLEAR')
    for offset in range(0, len(encoded), 96):
        power.serial(f"printf '%s' '{encoded[offset:offset+96]}' >> /tmp/a6-smp-soak.b64; echo A6_SOAK_CHUNK", 'A6_SOAK_CHUNK')
    output = power.serial('base64 -d /tmp/a6-smp-soak.b64 > /tmp/a6-smp-soak.sh; sha256sum /tmp/a6-smp-soak.sh; echo A6_SOAK_HASH', 'A6_SOAK_HASH')
    if digest not in output:
        raise SystemExit('soak script hash mismatch')
    power.serial(f'busybox setsid busybox sh /tmp/a6-smp-soak.sh {a.desktop_pid} </dev/null >/tmp/a6-soak-start.log 2>&1 & echo A6_SOAK_START', 'A6_SOAK_START')
    output = power.serial('sleep 2; pid=$(cat /tmp/a6-smp-soak.pid); kill -0 "$pid" && head -n 1 /tmp/a6-smp-soak.log && echo A6_SOAK_ALIVE', 'A6_SOAK_ALIVE')
    print(output)
    print('24-hour desktop soak running; script SHA-256', digest)
else:
    folder = ROOT / 'logs/smp'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-smp-desktop-soak.console.txt')
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'), 'cat /tmp/a6-smp-soak.log; echo A6_SOAK_COLLECT_END', '--until', 'A6_SOAK_COLLECT_END', '--timeout', '60'], capture_output=True, text=True, timeout=70)
    path.write_text(run.stdout + run.stderr)
    if run.returncode:
        raise SystemExit(f'partial soak capture retained: {path}')
    if 'A6_SMP_SOAK_V1 failed' in run.stdout:
        state = 'failed'
    elif 'A6_SMP_SOAK_V1 completed_samples=1441' in run.stdout:
        state = 'complete'
    elif ('A6_SMP_SOAK_USER_WRAP requested_after_11h' in run.stdout
          and 'A6_SMP_SOAK_V1 aborted' in run.stdout):
        state = 'wrapped at user request'
    elif 'A6_SMP_SOAK_V1 aborted' in run.stdout:
        state = 'aborted'
    else:
        state = 'in progress'
    print(f'Soak {state}; evidence saved: {path}')

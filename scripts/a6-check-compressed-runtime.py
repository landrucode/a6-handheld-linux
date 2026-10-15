#!/usr/bin/env python3
"""Isolate compressed-root reads and ELF execution before starting a desktop."""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'logs/ram-root'
    output.mkdir(parents=True, exist_ok=True)
    log = output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-runtime-check.log')
    captures = []
    stages = [
        ('preflight', 'test -x /tmp/graphics-runtime/bin/bash && '
         'cat /proc/mounts && cat /sys/devices/system/cpu/online'),
        ('read', '/bin/busybox sha256sum /tmp/graphics-runtime/bin/bash '
         '/tmp/graphics-runtime/usr/bin/Hyprland'),
        ('execute_cpu0', '/bin/busybox timeout 15 /bin/busybox taskset -c 0 '
         '/bin/busybox chroot /tmp/graphics-runtime /bin/bash --noprofile --norc '
         "-c 'printf COMPRESSED_ELF_CPU0_OK'"),
        ('execute_cpu1', '/bin/busybox timeout 15 /bin/busybox taskset -c 1 '
         '/bin/busybox chroot /tmp/graphics-runtime /bin/bash --noprofile --norc '
         "-c 'printf COMPRESSED_ELF_CPU1_OK'"),
        ('postflight', 'cat /sys/firmware/a6_charger_policy/status; '
         'cat /sys/firmware/a6_charger_policy/low_battery_status; cat /proc/interrupts'),
    ]
    try:
        for stage, command in stages:
            marker = 'A6_ROOT_' + stage.upper()
            captures.append('\nHOST_UTC=' + datetime.now(timezone.utc).isoformat() + '\nSTAGE=' + stage + '\n')
            command += '; result=$?; echo; echo ' + marker + '_RC=$result; echo ' + marker
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'),
                                  command, '--until', marker, '--timeout', '30'],
                                 text=True, capture_output=True, timeout=40)
            captures.append(run.stdout + run.stderr)
            log.write_text(''.join(captures))
            # Match the result line; the shell echoes the command itself too.
            lines = run.stdout.replace('\r', '').splitlines()
            if run.returncode or marker + '_RC=0' not in lines:
                raise RuntimeError('runtime stage failed: ' + stage)
    finally:
        log.write_text(''.join(captures))
        print('Compressed-root evidence:', log, flush=True)


if __name__ == '__main__':
    main()

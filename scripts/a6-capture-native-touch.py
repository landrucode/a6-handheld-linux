#!/usr/bin/env python3
"""Run one attended N42 frame capture; preserve evidence even on timeout."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', action='store_true', help='require frame-capture sysfs')
    parser.add_argument('--native', action='store_true', help='start persistent native input instead of bounded capture')
    args = parser.parse_args()
    if args.native and args.frames: parser.error('choose native input or bounded frames')
    folder = ROOT / 'logs/touch'
    folder.mkdir(exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-native-capture.console.txt')
    parts = []
    def command(text, timeout=20):
        marker = text.rsplit('echo ', 1)[1]
        parts.append('\nHOST_UTC=' + datetime.now(timezone.utc).isoformat() + '\n')
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'),
                              text, '--until', marker, '--timeout', str(timeout)],
                             text=True, capture_output=True, timeout=timeout+10)
        parts.append(run.stdout + run.stderr)
        path.write_text(''.join(parts))
        if run.returncode:
            raise RuntimeError('capture command failed; partial evidence retained: ' + str(path))
        return run.stdout
    try:
        test = 'test -r /sys/firmware/a6_touch_frames/status && echo A6_FRAME_SYSFS_PRESENT; ' if args.frames else ''
        if args.native: test = 'test -r /sys/firmware/a6_touch_native/status && echo A6_NATIVE_SYSFS_PRESENT; '
        health = command(test + 'cat /sys/devices/system/cpu/online; '
                         'cat /sys/firmware/a6_charger_policy/status; '
                         'cat /sys/firmware/a6_charger_policy/low_battery_status; echo A6_TOUCH_PREFLIGHT')
        if 'auto=1 paused=0 fault=0 ' not in health or 'enabled=1 ' not in health:
            raise RuntimeError('power protection preflight failed')
        if args.native and not re.search(r'^A6_NATIVE_SYSFS_PRESENT$', health.replace('\r', ''), re.M):
            raise RuntimeError('native input sysfs is absent')
        if args.frames and not re.search(r'^A6_FRAME_SYSFS_PRESENT$', health.replace('\r', ''), re.M):
            raise RuntimeError('frame capture sysfs is absent')
        command('echo enable-spi1 > /sys/firmware/a6_touch_transport/enable_clock; '
                'echo enable-pwm-gate > /sys/firmware/a6_touch_clock/enable_gate; '
                'cat /sys/firmware/a6_touch_transport/status; '
                'cat /sys/firmware/a6_touch_clock/status; echo A6_TOUCH_CLOCKS')
        operation = 'start-native-n42' if args.native else 'upload-and-calibrate-n42'
        command('echo ' + operation + ' > /sys/firmware/a6_touch_fw_n42/run; '
                'cat /sys/firmware/a6_touch_fw_n42/status; '
                'cat /sys/firmware/a6_touch_report_n42/status; echo A6_TOUCH_PROTOCOL', 110)
        if args.native:
            command('cat /sys/firmware/a6_touch_native/status; cat /sys/firmware/a6_touch_native/transfers; cat /proc/bus/input/devices; echo A6_NATIVE_REGISTERED')
        if args.frames:
            command('cat /sys/firmware/a6_touch_frames/status; test ! -r /sys/firmware/a6_touch_native/transfers || cat /sys/firmware/a6_touch_native/transfers; echo A6_TOUCH_FRAMES')
        command('cat /sys/firmware/a6_charger_policy/status; '
                'cat /sys/firmware/a6_charger_policy/low_battery_status; '
                'cat /proc/interrupts; echo A6_TOUCH_POSTFLIGHT')
    finally:
        path.write_text(''.join(parts))
        print('Touch evidence:', path, flush=True)


if __name__ == '__main__':
    main()

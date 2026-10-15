#!/usr/bin/env python3
"""Run one RAM-shell command over authenticated USB HTTP; never replay it."""
import argparse
import base64
import os
from pathlib import Path
import re
import stat
import secrets
import time
import sys
import urllib.request


def execute(command, token_path, timeout):
    with Path(token_path).open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('RPC token must be user-owned mode 600')
        token = stream.read(66).strip()
    if not re.fullmatch(rb'[0-9a-f]{64}', token) or not 1 <= len(command.encode()) <= 2048:
        raise ValueError('Invalid RPC token or command length')
    body = token + b'\n' + base64.b64encode(command.encode()) + b'\n'
    request = urllib.request.Request('http://192.168.7.2:8080/cgi-bin/a6-rpc.cgi',
                                     data=body, method='POST',
                                     headers={'Content-Type': 'text/plain'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout + 5) as response:
        data = response.read(2*1024*1024 + 1)
    if len(data) > 2*1024*1024:
        raise ValueError('RPC output bound exceeded')
    match = re.search(rb'\nA6_USB_RPC_RC=(\d+)\n$', data)
    if not match:
        raise ValueError('RPC completion missing; command will not be replayed')
    return int(match[1]), data[:match.start()].decode(errors='replace')


def capture_incident(token_path):
    """Read state before recovery; omit argv to avoid encoded-secret echoes."""
    command = (
        'echo INCIDENT_UPTIME; cat /proc/uptime; '
        'echo PROCESSES; busybox ps -o pid,ppid,stat,comm; '
        'echo POWER; cat /sys/firmware/a6_charger_policy/status '
        '/sys/firmware/a6_charger_policy/low_battery_status; '
        'echo GADGET; for field in state current_speed function; do '
        'printf "%s=" "$field"; cat /sys/class/udc/36100000.usb/$field; done; '
        'echo USB_STAGE; cat /sys/class/udc/36100000.usb/device/a6_usb_stage '
        '/sys/class/udc/36100000.usb/device/a6_lx_latch 2>/dev/null; '
        'echo DMESG; dmesg; echo POWER_HISTORY; '
        'busybox tail -n 120 /tmp/a6-power-longrun.log 2>/dev/null; '
        'echo POWER_PROBE; busybox tail -n 120 /tmp/a6-power-probe.private.log 2>/dev/null; true')
    rc, output = execute(command, token_path, 3)
    if rc:
        raise RuntimeError('Incident collection failed')
    root = Path(__file__).resolve().parents[1]
    path = root/'build/session-logs'/('wifi-http-incident-' +
            str(int(time.time())) + '-' + secrets.token_hex(4) + '.private.log')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(output)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command')
    p.add_argument('--until')
    p.add_argument('--timeout', type=int, default=110)
    args = p.parse_args()
    try:
        if not 1 <= args.timeout <= 120:
            raise ValueError('Timeout outside bound')
        rc, output = execute(args.command, os.environ['A6_USB_HTTP_RPC_TOKEN'], args.timeout)
        # Existing serial collectors expect output to start on a fresh line.
        sys.stdout.write("\n" + output)
        if args.until and args.until not in output.splitlines():
            rc = 1
        return rc
    except Exception:
        sys.stderr.write('USB HTTP RPC failed; command not replayed\n')
        return 1


if __name__ == '__main__':
    sys.exit(main())

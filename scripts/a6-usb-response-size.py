#!/usr/bin/env python3
"""Bounded raw TCP response-size trial on USB only; private logs, no HTTP."""
import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import socket
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 3:
        parser.error('--repeats must be 1..3')
    os.environ.pop('A6_USB_HTTP_RPC_TOKEN', None)
    os.environ['A6_ACM_BROKER'] = str(ROOT/'build/wifi-native/acm.sock')
    spec = importlib.util.spec_from_file_location('connection', ROOT/'scripts/a6-wifi-connect.py')
    connection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(connection)
    phone = connection.Phone()
    path = ROOT/'build/session-logs'/('usb-response-size-' + str(int(time.time())) + '.private.log')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    sizes = (511,512,513,4095,4096,4097,8191,8192,8193,16383,16384,16385,
             32767,32768,32769,65535,65536,65537,131072)
    stem = '/tmp/a6-usb-size'
    failures = 0
    with os.fdopen(fd, 'w', buffering=1) as log:
        for size in sizes * args.repeats:
            command = 'EXEC:busybox head -c ' + str(size) + ' /dev/zero'
            phone.checked('busybox setsid busybox timeout 12 ' + connection.SOCAT +
                          ' TCP4-LISTEN:8082,bind=192.168.7.2,reuseaddr ' + shlex.quote(command) +
                          ' </dev/null >' + stem + '.log 2>&1 & echo $! >' + stem + '.pid; sleep 1')
            data = bytearray()
            error = ''
            started = time.monotonic()
            try:
                with socket.create_connection(('192.168.7.2',8082),timeout=2) as sock:
                    sock.settimeout(2)
                    while len(data) <= size:
                        part = sock.recv(65536)
                        if not part:
                            break
                        data.extend(part)
            except OSError as exc:
                error = type(exc).__name__
            good = len(data) == size and not any(data) and not error
            log.write('SIZE=' + str(size) + ' BYTES=' + str(len(data)) + ' PASS=' + str(good) +
                      ' ERROR=' + error + ' SECONDS=' + str(time.monotonic()-started) + '\n')
            print('Raw USB TCP size ' + str(size) + ': ' + ('pass' if good else 'FAIL received ' + str(len(data))),flush=True)
            if not good:
                failures += 1
                raw = path.with_name(path.stem + '-' + str(size) + '-' + str(time.time_ns()) + '.private.raw')
                raw_fd = os.open(raw, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(raw_fd, 'wb') as stream:
                    stream.write(data)
                try:
                    log.write(phone.checked(connection.SS + ' -tn; cat /proc/net/dev; dmesg'))
                except RuntimeError:
                    log.write('ACM_UNAVAILABLE; no recovery attempted\n')
                    print('ACM unavailable; trial stopped without recovery', flush=True)
                    break
            phone.serial('busybox kill -TERM -$(cat ' + stem + '.pid) 2>/dev/null; true')
            if not good:
                # Explicit bounded diagnostic recovery, only after evidence.
                phone.checked('busybox ifconfig usb0 down; busybox ifconfig usb0 192.168.7.2 netmask 255.255.255.252 up')
                if failures >= 6:
                    break
    print('Raw-size trial finished; failing sizes: ' + str(failures),flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

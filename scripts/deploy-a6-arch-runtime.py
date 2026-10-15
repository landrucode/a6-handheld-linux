#!/usr/bin/env python3
"""Upload the prepared Arch runtime over USB Ethernet and test it in phone RAM."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import secrets
import select
import socket
import termios
import time
import tty

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('device', nargs='?', default='/dev/ttyACM0')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
bundle = repo / 'build/arch-bootstrap/arch-runtime.tar.gz'
payload = bundle.read_bytes()
digest = hashlib.sha256(payload).hexdigest()
expected = (bundle.parent / 'arch-runtime.sha256').read_text().split()[0]
if digest != expected or not 0 < len(payload) < 8 * 1024 * 1024:
    raise RuntimeError('prepare and verify the Arch runtime before deploying')
node = Path(args.device)
if node.parent != Path('/dev') or not node.name.startswith('ttyACM'):
    raise RuntimeError('expected /dev/ttyACM device')
device = Path('/sys/class/tty', node.name, 'device').resolve()
usb = next(p for p in (device, *device.parents) if (p / 'idVendor').exists())
if (usb.name, (usb / 'idVendor').read_text().strip(),
        (usb / 'idProduct').read_text().strip()) != ('1-5', '0525', 'a4aa'):
    raise RuntimeError('expected A6 ECM/ACM gadget on USB port 1-5')
token = secrets.token_hex(8)
remote = '/tmp/a6-arch-' + token
log_path = repo / 'build/session-logs' / ('arch-deploy-' + token + '.raw')
log_path.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
exclusive = False
listener = False
with log_path.open('xb') as log:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        exclusive = True
        tty.setraw(fd, termios.TCSANOW)

        def transaction(body, label, timeout=20):
            marker = ('A6-ARCH-' + token + '-' + label).encode()
            command = (body + "; a6_status=$?; printf '\\n%s%s %s\\n' 'A6-ARCH-' '" +
                       token + '-' + label + "' \"$a6_status\"\n").encode()
            data = bytearray()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                readable, writable, _ = select.select([fd], [fd] if command else [], [], 0.2)
                if writable:
                    try:
                        command = command[os.write(fd, command):]
                    except BlockingIOError:
                        pass
                if readable:
                    try:
                        chunk = os.read(fd, 8192)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise RuntimeError('serial disconnected')
                    log.write(chunk)
                    log.flush()
                    data.extend(chunk)
                    if len(data) > 1024 * 1024:
                        raise RuntimeError('unexpected volume of serial output')
                    lines = bytes(data).replace(b'\r', b'').split(b'\n')[:-1]
                    records = [line for line in lines if line.startswith(marker + b' ')]
                    if records:
                        if records != [marker + b' 0']:
                            raise RuntimeError(f'{label} failed; see {log_path}')
                        return lines
            raise RuntimeError(f'{label} timed out; see {log_path}')

        # Cancel a partial command and issue a fresh challenge. Marker fragments
        # are separate in transmitted text so terminal echo cannot satisfy it.
        os.write(fd, b'\x03\n')
        transaction('true', 'ready')
        transaction('ram_ok=1; while read -r src dst fs rest; do '
                    'case "$fs" in rootfs|devtmpfs|proc|sysfs) ;; *) ram_ok=0;; esac; '
                    'done < /proc/mounts; test "$ram_ok" = 1 && '
                    'test -d /tmp && test ! -L /tmp', 'ram')
        transaction(f'/bin/busybox mkdir {remote}', 'mkdir')
        transaction(f'/bin/busybox nc -l -p 8082 > {remote}/runtime.tar.gz & '
                    'a6_upload_pid=$!; test "$a6_upload_pid" -gt 1', 'listen')
        listener = True
        with socket.create_connection(('192.168.7.2', 8082), timeout=10) as connection:
            connection.settimeout(60)
            connection.sendall(payload)
            connection.shutdown(socket.SHUT_WR)
            while connection.recv(1024):
                pass
        transaction('wait "$a6_upload_pid"', 'upload')
        listener = False
        lines = transaction(f'/bin/busybox sha256sum {remote}/runtime.tar.gz', 'hash')
        if f'{digest}  {remote}/runtime.tar.gz'.encode() not in lines:
            raise RuntimeError('phone upload checksum mismatch; not extracting')
        transaction(f'/bin/busybox tar -xzf {remote}/runtime.tar.gz -C {remote}', 'extract')
        lines = transaction(f'/bin/busybox chroot {remote}/arch-runtime '
                            '/bin/bash --noprofile --norc /arch-smoke.sh', 'test')
        if b'ARCH ARRAYS FORK EXEC PIPE WAIT SIGNAL CLOCK PASS' not in lines:
            raise RuntimeError('missing Arch smoke-test success record')
        print('PASS: verified Arch runtime deployed and tested in phone RAM.')
        print('Serial log:', log_path)
        print('Phone command: /bin/busybox chroot ' + remote +
              '/arch-runtime /bin/bash --noprofile --norc')
    finally:
        if listener:
            try:
                transaction('kill "$a6_upload_pid"', 'cleanup', timeout=2)
            except Exception:
                pass
        if exclusive:
            fcntl.ioctl(fd, termios.TIOCNXCL)
        os.close(fd)

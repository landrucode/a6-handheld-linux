#!/usr/bin/env python3
"""Send text or a key to XTerm or nested Weston through verified USB serial.

Requires the graphics runtime and arch-input overlay. No reboot or daemon.
Text is typed literally; --enter executes it in the focused graphical shell. With --target weston, the active Wayland client
receives input; ensure the intended terminal is focused.
"""
import argparse
import fcntl
import os
from pathlib import Path
import re
import secrets
import subprocess
import select
import shlex
import termios
import time
import tty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=['serial', 'ssh'], default='serial',
                        help='serial recovery channel or authenticated USB SSH')
    parser.add_argument('--device', default='/dev/ttyACM0')
    parser.add_argument('--target', choices=['xterm', 'weston'], default='xterm',
                        help='XTerm or the focused native client inside nested Weston')
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--text', help='up to 256 printable ASCII characters')
    actions.add_argument('--key', choices=['Return', 'BackSpace', 'Tab', 'Escape', 'Up', 'Down', 'Left', 'Right', 'Home', 'End', 'ctrl+c', 'ctrl+d', 'ctrl+l', 'ctrl+o', 'ctrl+x'])
    parser.add_argument('--enter', action='store_true', help='press Return after text')
    args = parser.parse_args()
    if args.enter and args.text is None:
        parser.error('--enter requires --text')
    if args.text is not None and (not 0 < len(args.text) <= 256 or any(not 32 <= ord(c) <= 126 for c in args.text)):
        parser.error('text must contain 1–256 printable ASCII characters')
    prefix = 'DISPLAY=:0 ' + ('/bin/busybox chroot /tmp/graphics-runtime ' if args.transport == 'serial' else '') + '/usr/bin/xdotool '
    window_class = '^XTerm$' if args.target == 'xterm' else 'weston'
    setup = 'input_window=$(' + prefix + 'search --class ' + shlex.quote(window_class) + ') && case "$input_window" in ""|*[!0-9]*) false;; *) ' + prefix + 'windowfocus "$input_window";; esac'
    action = 'type --clearmodifiers --delay 12 -- ' + shlex.quote(args.text) if args.text is not None else 'key --clearmodifiers ' + shlex.quote(args.key)
    command = setup + ' && ' + prefix + action
    if args.enter:
        command += ' && ' + prefix + 'key Return'
    if args.transport == 'ssh':
        subprocess.run([str(Path(__file__).resolve().parent / 'a6-ssh'), command],
                       check=True, timeout=30)
        print('Sent to phone ' + args.target + ' via SSH.' + (' Return pressed.' if args.enter else ''))
        return
    node = Path(args.device)
    if node.parent != Path('/dev') or not re.fullmatch(r'ttyACM[0-9]+', node.name):
        parser.error('expected /dev/ttyACM device')
    path = Path('/sys/class/tty', node.name, 'device').resolve()
    usb = next((p for p in (path, *path.parents) if (p / 'idVendor').exists()), None)
    if usb is None or usb.name != '1-5' or ((usb / 'idVendor').read_text().strip(), (usb / 'idProduct').read_text().strip()) != ('0525', 'a4aa'):
        parser.error('not the verified A6 composite gadget on USB port 1-5')
    fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        tty.setraw(fd, termios.TCSANOW)
        def exchange(body):
            token = secrets.token_hex(12)
            marker = ('A6-INPUT-' + token).encode()
            command = (body + "; input_status=$?; printf '\\n%s%s %s\\n' 'A6-INPUT-' " + shlex.quote(token) + ' "$input_status"\n').encode()
            pending = memoryview(command)
            received = bytearray()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                reads, writes, _ = select.select([fd], [fd] if pending else [], [], .2)
                if writes:
                    try:
                        pending = pending[os.write(fd, pending):]
                    except BlockingIOError:
                        pass
                if reads:
                    chunk = os.read(fd, 8192)
                    if not chunk:
                        raise RuntimeError('USB disconnected; do not automatically retry input')
                    received.extend(chunk)
                    for line in bytes(received).replace(b'\r', b'').split(b'\n')[:-1]:
                        if line.startswith(marker + b' '):
                            if line != marker + b' 0':
                                raise RuntimeError('phone command failed: ' + received.decode(errors='replace'))
                            return
            raise RuntimeError('input result unknown after timeout; do not automatically retry')
        # A fresh split marker prevents terminal echo from proving execution.
        exchange('true')
        exchange(command)
        print('Sent to phone ' + args.target + '.' + (' Return pressed.' if args.enter else ''))
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Interactive terminal for the verified A6 RAM shell; Ctrl-] disconnects."""
import argparse
import fcntl
import os
from pathlib import Path
import select
import sys
import termios
import tty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', nargs='?', default='/dev/ttyACM0')
    parser.add_argument('--raw-log', type=Path, help='create a new file of received USB bytes')
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error('run this terminal from an interactive host terminal')
    node = Path(args.device)
    if node.parent != Path('/dev') or not node.name.startswith('ttyACM'):
        parser.error('expected /dev/ttyACM device')
    path = Path('/sys/class/tty', node.name, 'device').resolve()
    usb = next((p for p in (path, *path.parents) if (p / 'idVendor').exists()), None)
    if usb is None or usb.name != '1-5' or ((usb / 'idVendor').read_text().strip(), (usb / 'idProduct').read_text().strip()) not in {('1209', '0001'), ('0525', 'a4aa')}:
        parser.error('device is not the verified A6 serial/composite gadget on port 1-5')
    saved = termios.tcgetattr(sys.stdin.fileno())
    fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    log = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        if args.raw_log:
            log = args.raw_log.open('xb')
        tty.setraw(fd, termios.TCSANOW)
        print('Connected. Ctrl-] disconnects; Ctrl-C goes to the phone.', flush=True)
        tty.setraw(sys.stdin.fileno(), termios.TCSANOW)
        pending = bytearray()
        while True:
            reads = [fd] + ([sys.stdin.fileno()] if len(pending) < 65536 else [])
            readable, writable, _ = select.select(reads, [fd] if pending else [], [], 0.5)
            if fd in readable:
                try:
                    chunk = os.read(fd, 8192)
                except BlockingIOError:
                    chunk = None
                if chunk == b'':
                    raise RuntimeError('USB disconnected')
                if chunk:
                    if log:
                        log.write(chunk)
                        log.flush()
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
            if sys.stdin.fileno() in readable:
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk or b'\x1d' in chunk:
                    break
                pending.extend(chunk)
            if fd in writable:
                try:
                    count = os.write(fd, pending)
                    del pending[:count]
                except BlockingIOError:
                    pass
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, saved)
        if log:
            log.close()
        # Keep serial host echo off to avoid feeding phone output back as input.
        os.close(fd)
    print('\nDisconnected; phone left running.')


if __name__ == '__main__':
    main()

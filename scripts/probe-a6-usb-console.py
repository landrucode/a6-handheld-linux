#!/usr/bin/env python3
"""Read A6 Linux console and prove a PID1 round trip on this phone only."""
import argparse
import os
from pathlib import Path
import secrets
import select
import sys
import termios
import time
import tty

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("device", help="host ACM node, e.g. /dev/ttyACM0")
parser.add_argument("--resume", action="store_true",
                    help="test an already-running PID1 without requiring its startup banner")
args = parser.parse_args()
node = Path(args.device)
if node.parent != Path("/dev") or not node.name.startswith("ttyACM"):
    parser.error("expected an explicit /dev/ttyACM device")
usb = Path("/sys/class/tty", node.name, "device").resolve()
for parent in [usb, *usb.parents]:
    if (parent / "idVendor").exists():
        usb = parent
        break
else:
    parser.error("no USB parent for that tty")
if (usb.name != "1-5" or (usb / "idVendor").read_text().strip() != "1209"
        or (usb / "idProduct").read_text().strip() != "0001"):
    parser.error("not the A6 diagnostic on the verified physical USB port")
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
old = termios.tcgetattr(fd)
try:
    tty.setraw(fd, termios.TCSANOW)
    captured = bytearray()
    deadline = time.monotonic() + 20
    marker = b"A6 Linux PID 1: Lightning USB serial is alive."
    while not args.resume and time.monotonic() < deadline and marker not in captured:
        if select.select([fd], [], [], 0.5)[0]:
            data = os.read(fd, 8192)
            if not data:
                raise RuntimeError("console disconnected")
            captured.extend(data)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    if not args.resume and marker not in captured:
        raise RuntimeError("no PID1 banner: no round-trip claim")
    nonce = ("A6-roundtrip-" + secrets.token_hex(16) + "\n").encode()
    print(f"Sending fresh token: {nonce.decode().strip()}", flush=True)
    sent = os.write(fd, nonce)
    if sent != len(nonce):
        raise RuntimeError("short host write: no round-trip claim")
    reply = bytearray()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and nonce not in reply:
        if select.select([fd], [], [], 0.5)[0]:
            data = os.read(fd, 8192)
            if not data:
                raise RuntimeError("console disconnected")
            reply.extend(data)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
    if nonce not in reply or b"PID1 RX: " not in reply:
        raise RuntimeError("PID1 round trip timed out")
    print("\nPASS: fresh nonce and PID1 reply prefix returned with host echo disabled."
          if args.resume else "\nPASS: PID1 banner and fresh nonce returned with host echo disabled.")
finally:
    try:
        termios.tcsetattr(fd, termios.TCSANOW, old)
    finally:
        os.close(fd)

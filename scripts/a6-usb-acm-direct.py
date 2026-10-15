"""Run one A6 RAM-shell command through the wheel-accessible USB ACM node.

The gadget udev rule grants wheel access to the USB device even when the
kernel-created /dev/ttyACM0 has no ACL. This helper briefly detaches only
the CDC ACM data interface, then reattaches its control interface in finally.
It does not modify phone storage or the host USB network configuration.
"""
import argparse
from pathlib import Path
import ctypes as C
import sys
import time
import shlex
import os
import json
import socket

# Explicit alternative transport, with no ambiguous automatic replay.
if os.environ.get('A6_USB_HTTP_RPC_TOKEN'):
    os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name('a6-usb-http-rpc.py')), *sys.argv[1:]])

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('command', help='single command line to send to the A6 RAM shell')
parser.add_argument('--until', help='standalone output marker that ends capture')
parser.add_argument('--timeout', type=int, default=110, help='maximum capture seconds')
args = parser.parse_args()
if not 1 <= args.timeout <= 120:
    parser.error('--timeout must be between 1 and 120 seconds')
if args.until and ('\n' in args.until or '\r' in args.until):
    parser.error('--until must be a single output line')

# Optional attended broker holds the raw interface across successive commands,
# and drains console traffic while idle. Never fall back to another detach if
# this explicitly selected session fails.
broker = os.environ.get('A6_ACM_BROKER')
if broker:
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
            peer.settimeout(args.timeout+10);peer.connect(broker)
            peer.sendall(json.dumps({'command':args.command,'until':args.until,
                                    'timeout':args.timeout}).encode()+b'\n')
            response=bytearray()
            while b'\n' not in response:
                chunk=peer.recv(65536)
                if not chunk or len(response)+len(chunk)>4*1024*1024:
                    raise RuntimeError('Invalid broker response')
                response.extend(chunk)
            result=json.loads(response.split(b'\n',1)[0])
        sys.stdout.write(result['stdout']);sys.stderr.write(result['stderr'])
        sys.exit(result['returncode'])
    except Exception:
        sys.exit('Persistent ACM transport failed; command omitted')

lib = C.CDLL('libusb-1.0.so.0')
ctx = C.c_void_p()
handle = C.c_void_p()
lib.libusb_init.argtypes = [C.POINTER(C.c_void_p)]
lib.libusb_init.restype = C.c_int
lib.libusb_open_device_with_vid_pid.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16]
lib.libusb_open_device_with_vid_pid.restype = C.c_void_p
lib.libusb_kernel_driver_active.argtypes = [C.c_void_p, C.c_int]
lib.libusb_kernel_driver_active.restype = C.c_int
lib.libusb_detach_kernel_driver.argtypes = [C.c_void_p, C.c_int]
lib.libusb_detach_kernel_driver.restype = C.c_int
lib.libusb_attach_kernel_driver.argtypes = [C.c_void_p, C.c_int]
lib.libusb_attach_kernel_driver.restype = C.c_int
lib.libusb_claim_interface.argtypes = [C.c_void_p, C.c_int]
lib.libusb_claim_interface.restype = C.c_int
lib.libusb_release_interface.argtypes = [C.c_void_p, C.c_int]
lib.libusb_release_interface.restype = C.c_int
lib.libusb_bulk_transfer.argtypes = [C.c_void_p, C.c_ubyte, C.c_void_p,
                                     C.c_int, C.POINTER(C.c_int), C.c_uint]
lib.libusb_bulk_transfer.restype = C.c_int
lib.libusb_close.argtypes = [C.c_void_p]
lib.libusb_exit.argtypes = [C.c_void_p]

command = args.command
# The interactive shell wraps echoed input at its terminal width. A trailing
# "echo MARKER" can consequently appear as a standalone marker before the
# command executes. Split the marker in the transmitted command so only its
# real printf output can satisfy the completion check.
if args.until and command.endswith('echo ' + args.until):
    split = max(1, len(args.until) // 2)
    command = command[:-len('echo ' + args.until)] + "printf '%s%s\\n' " + \
        shlex.quote(args.until[:split]) + ' ' + shlex.quote(args.until[split:])
marker = args.until.encode() if args.until else None
detached = claimed = False
code = lib.libusb_init(C.byref(ctx))
if code:
    raise RuntimeError(f'libusb_init {code}')
try:
    handle = lib.libusb_open_device_with_vid_pid(ctx, 0x0525, 0xa4aa)
    if not handle:
        raise RuntimeError('A6 gadget not found or inaccessible')
    active = lib.libusb_kernel_driver_active(handle, 3)
    if active < 0:
        raise RuntimeError(f'kernel_driver_active {active}')
    if active:
        code = lib.libusb_detach_kernel_driver(handle, 3)
        if code:
            raise RuntimeError(f'detach {code}')
        detached = True
    code = lib.libusb_claim_interface(handle, 3)
    if code:
        raise RuntimeError(f'claim {code}')
    claimed = True
    payload = (command + '\n').encode()
    buf = (C.c_ubyte * len(payload)).from_buffer_copy(payload)
    transferred = C.c_int()
    code = lib.libusb_bulk_transfer(handle, 0x04, buf, len(payload),
                                    C.byref(transferred), 3000)
    if code or transferred.value != len(payload):
        raise RuntimeError(f'write {code} {transferred.value}/{len(payload)}')
    end = time.monotonic() + (args.timeout if marker else min(args.timeout, 5))
    tail = bytearray()
    found = False
    while time.monotonic() < end:
        buf = (C.c_ubyte * 8192)()
        transferred = C.c_int()
        code = lib.libusb_bulk_transfer(handle, 0x85, buf, len(buf),
                                        C.byref(transferred), 500)
        if code not in (0, -7):
            raise RuntimeError(f'read {code}')
        sys.stdout.buffer.write(bytes(buf[:transferred.value]))
        sys.stdout.buffer.flush()
        if marker:
            tail.extend(bytes(buf[:transferred.value]))
            if b'\n' + marker + b'\r' in tail:
                found = True
                break
            tail = tail[-2048:]
    if marker and not found:
        raise TimeoutError(f'output marker {args.until!r} was not received')
finally:
    if handle:
        if claimed:
            code = lib.libusb_release_interface(handle, 3)
            if code:
                print(f'warning: release ACM data interface: {code}', file=sys.stderr)
        if detached:
            # cdc_acm binds on control interface 2 and claims data interface 3.
            code = lib.libusb_attach_kernel_driver(handle, 2)
            if code and lib.libusb_kernel_driver_active(handle, 2) != 1:
                print(f'warning: reattach ACM control interface: {code}', file=sys.stderr)
        lib.libusb_close(handle)
    lib.libusb_exit(ctx)

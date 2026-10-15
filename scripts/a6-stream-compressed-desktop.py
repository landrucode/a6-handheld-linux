#!/usr/bin/env python3
"""Transfer the verified SquashFS to RAM and mount its writable overlay."""
import argparse
import hashlib
from pathlib import Path
import secrets
import socket
import time

from importlib.util import spec_from_file_location, module_from_spec

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('desktop_transport', ROOT / 'scripts/a6-stream-user-desktop.py')
transport = module_from_spec(spec)
spec.loader.exec_module(transport)
serial = transport.serial
IMAGE = ROOT / 'build/arch-bootstrap/arch-hyprland-user-desktop.squashfs'
EXPECTED = '7520a8990582ae06c1c42c4338796d218b816e95538a18e0ce94b15cb1091864'


def upload_ram_helper(source, destination):
    """Stream one small helper to a fixed RAM path, then verify before use."""
    if destination not in ('/tmp/a6-mount-compressed.sh',
                           '/tmp/graphics-runtime/usr/local/bin/a6-label-native-touch'):
        raise ValueError('helper destination must be an approved RAM path')
    blob = source.read_bytes()
    if not 0 < len(blob) <= 8192:
        raise ValueError('helper size exceeds the bounded transfer')
    nonce = secrets.token_hex(4)
    status = '/tmp/a6-helper-' + nonce + '.status'
    worker = f'busybox timeout 15 busybox nc -l -p 8083 > {destination}; echo $? > {status}'
    serial(f"busybox setsid busybox sh -c '{worker}' </dev/null "
           '>/tmp/a6-helper-stream.log 2>&1 & echo A6_HELPER_LISTENING',
           'A6_HELPER_LISTENING')
    # A listener may still be starting when the serial marker arrives.
    deadline = time.monotonic() + 5
    while True:
        try:
            target = socket.create_connection(('192.168.7.2', 8083), timeout=1)
            break
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    with target:
        target.settimeout(10)
        target.sendall(blob)
        target.shutdown(socket.SHUT_WR)
    digest = hashlib.sha256(blob).hexdigest()
    serial(f"sleep 1; test -f {status} && test \"$(cat {status})\" = 0 && "
           f"printf '%s  %s\\n' '{digest}' {destination} | busybox sha256sum -c - "
           '&& echo A6_HELPER_VERIFIED', 'A6_HELPER_VERIFIED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'deploy'))
    parser.add_argument('--native', action='store_true', help='use the verified native keyboard SquashFS')
    args = parser.parse_args()
    image = (ROOT / 'build/arch-bootstrap/arch-hyprland-user-desktop-native.squashfs'
             if args.native else IMAGE)
    expected = ('88d9362f58826f5154d2548edfe86c44b63e7f121ebc3804eb50402a85cf394e'
                if args.native else EXPECTED)
    assert image.stat().st_size == 117739520, 'image size changed'
    assert hashlib.file_digest(image.open('rb'), 'sha256').hexdigest() == expected, 'image hash changed'
    print('Verified compressed desktop:', image.stat().st_size, expected)
    if args.action == 'check':
        return
    serial("test ! -e /tmp/graphics-runtime && test ! -e /tmp/a6-desktop.squashfs && "
           "grep -q squashfs /proc/filesystems && grep -q overlay /proc/filesystems && "
           "grep -q '^auto=1 paused=0 fault=0 ' /sys/firmware/a6_charger_policy/status && "
           "grep -q 'enabled=1 ' /sys/firmware/a6_charger_policy/low_battery_status && "
           "echo A6_COMPRESSED_PREFLIGHT", 'A6_COMPRESSED_PREFLIGHT')
    nonce = secrets.token_hex(4)
    status = '/tmp/a6-compressed-' + nonce + '.status'
    worker = (f'/bin/busybox nc -l -p 8082 > /tmp/a6-desktop.squashfs; echo $? > {status}')
    serial(f"/bin/busybox setsid /bin/busybox sh -c '{worker}' </dev/null "
           ">/tmp/a6-compressed-stream.log 2>&1 & echo A6_COMPRESSED_LISTENING", 'A6_COMPRESSED_LISTENING')
    with socket.create_connection(('192.168.7.2', 8082), timeout=10) as target:
        target.settimeout(60)
        with image.open('rb') as source:
            for block in iter(lambda: source.read(65536), b''):
                target.sendall(block)
                time.sleep(0.0625)
        target.shutdown(socket.SHUT_WR)
    serial(f"sleep 1; test -f {status} && test \"$(cat {status})\" = 0 && "
           "echo A6_COMPRESSED_TRANSFERRED", 'A6_COMPRESSED_TRANSFERRED')
    upload_ram_helper(ROOT / 'rootfs/a6-mount-compressed-desktop.sh',
                      '/tmp/a6-mount-compressed.sh')
    profile = 'native' if args.native else 'baseline'
    serial('busybox sh /tmp/a6-mount-compressed.sh ' + profile + ' && echo A6_COMPRESSED_READY',
           'A6_COMPRESSED_READY', timeout=110)
    upload_ram_helper(ROOT / 'rootfs/a6-label-native-touch.sh',
                      '/tmp/graphics-runtime/usr/local/bin/a6-label-native-touch')
    print('Compressed RAM desktop mounted; provision the accepted unprivileged desktop next.')


if __name__ == '__main__':
    main()

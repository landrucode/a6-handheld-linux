#!/usr/bin/env python3
"""Generate RAM-only shell initramfs manifest from pinned ARM soft-float ELF."""
from pathlib import Path
import hashlib
import os
import struct
import sys

repo, init, manifest = map(Path, sys.argv[1:])
binary = repo / '.deps/busybox/armel/bin/busybox'
data = binary.read_bytes()
assert hashlib.sha256(data).hexdigest() == '98fb02116495550c10073f3b793ca84cdbafb65b1bba0ae3f76f3105f4f85572'
assert data[:7] == b'\x7fELF\x01\x01\x01'
assert struct.unpack_from('<H', data, 18)[0] == 40
assert struct.unpack_from('<I', data, 36)[0] & 0x600 == 0x200
phoff = struct.unpack_from('<I', data, 28)[0]
entsize, count = struct.unpack_from('<HH', data, 42)
assert all(struct.unpack_from('<I', data, phoff+i*entsize)[0] != 3 for i in range(count))
lines = [f'dir /{name} 0755 0 0' for name in ('dev', 'proc', 'sys', 'bin', 'sbin', 'tmp', 'etc')]
lines += ['nod /dev/console 0600 0 0 c 5 1',
          f'file /init {init} 0755 0 0', f'file /bin/busybox {binary} 0755 0 0']
for name in ('sh', 'ash', 'cat', 'ls', 'uname', 'ps', 'dmesg', 'mount', 'echo',
             'printf', 'pwd', 'sleep', 'head', 'tail', 'wc', 'grep', 'stty', 'mkdir'):
    lines.append(f'slink /bin/{name} busybox 0777 0 0')
if os.environ.get('A6_USB_NETWORK') == '1':
    lines += ['dir /www 0755 0 0',
              f'file /etc/a6-network.sh {repo / "rootfs/a6-network.sh"} 0755 0 0',
              f'file /www/index.html {repo / "rootfs/a6-network-index.html"} 0644 0 0']
    for name in ('ip', 'ifconfig', 'httpd', 'wget', 'nc', 'tar', 'base64', 'sha256sum', 'ping'):
        lines.append(f'slink /bin/{name} busybox 0777 0 0')
if os.environ.get('A6_WIFI_BOOT_DEFAULTS') == '1':
    assert os.environ.get('A6_WIFI_NATIVE') == '1'
    lines.append('dir /etc/a6-boot 0755 0 0')
    for name in ('a6-wifi-boot.sh','a6-wifi-common.sh','a6-wifi-off.sh',
                 'a6-wifi-dhcp.sh','a6-vendor-data.awk','a6-wifi.nft',
                 'a6-mount-compressed-desktop.sh','a6-label-native-touch.sh','a6-prepare-user-desktop.sh','a6-start-desktop.sh','a6-start-native-desktop.sh','a6-verify-update.sh'):
        lines.append(f'file /etc/{name} {repo / "rootfs" / name} 0755 0 0')
    if os.environ.get('A6_AUDIO_FIFO_DISCOVER') == '1':
        lines.append(f'file /etc/a6-usb-upload-recover.sh {repo / "rootfs/a6-usb-upload-recover.sh"} 0755 0 0')
    assets=repo/'build/wifi-boot-assets'
    for path in sorted(assets.glob('*.ioctl'))+sorted(assets.glob('*.prefix')):
        lines.append(f'file /etc/a6-boot/{path.name} {path} 0644 0 0')
    lines.append(f'file /etc/a6-boot/desktop.sha256 {assets/"desktop.sha256"} 0644 0 0')
    lines.append(f'file /etc/a6-update-public.pem {assets/"update-public.pem"} 0644 0 0')
manifest.write_text('\n'.join(lines) + '\n')
print('PASS: pinned static ARM soft-float BusyBox; RAM-only shell manifest')

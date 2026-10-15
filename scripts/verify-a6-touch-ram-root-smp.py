#!/usr/bin/env python3
"""Verify the isolated touch/RAM-root build without relaxing older checks."""
import hashlib
import json
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--frames', action='store_true')
parser.add_argument('--native', action='store_true')
args = parser.parse_args()
if args.native: args.frames = True
KIND = 'low-battery-boot-defaults-touch-ram-root' + ('-frames' if args.frames else '') + ('-native' if args.native else '') + '-smp-first-scheduling'
build = ROOT / ('build/linux-a6-' + KIND)
config = (build / '.config').read_text()
linked = (build / 'vmlinux').read_bytes()
for symbol in ('SMP', 'BLOCK', 'BLK_DEV_LOOP', 'SQUASHFS', 'SQUASHFS_ZSTD',
               'OVERLAY_FS', 'TMPFS_XATTR', 'SWAP', 'ZSMALLOC', 'ZRAM',
               'ZRAM_BACKEND_LZ4', 'ZRAM_DEF_COMP_LZ4', 'INPUT_EVDEV'):
    assert f'CONFIG_{symbol}=y\n' in config, symbol
for symbol in ('HOTPLUG_CPU', 'CPU_IDLE', 'ZRAM_WRITEBACK', 'KEXEC'):
    assert f'CONFIG_{symbol}=y\n' not in config, symbol
packet = (ROOT / 'build/touch-research/N42-constructed-firmware.bin').read_bytes()
assert len(packet) == 64340
assert hashlib.sha256(packet).hexdigest() == 'af78e1a4033c213747c2e76f7b55e38bfdc4b1f1590a6ab0b07f7fc5ff9420c3'
assert linked.count(packet) == 1
old = (ROOT / 'build/linux-a6-touch-e3-info-n42/vmlinux').read_bytes()
manifest = json.loads((ROOT / 'build/touch-research/n42-calibration-packets.json').read_text())
import re
generated = (ROOT / 'build/touch-research/n42-calibration-packets.inc').read_text()
for item in manifest['packets']:
    match = re.search(r'static const u8 ' + item['name'] + r'\[\] = \{(.*?)\};', generated, re.S)
    assert match
    data = bytes(int(v, 16) for v in re.findall(r'0x([0-9a-f]{2})', match[1]))
    assert len(data) == item['packet_bytes']
    assert linked.count(data) == old.count(data) == 1
for marker in (b'A6_TOUCH_N42_FW_V1', b'A6_TOUCH_N42_POST_V1',
               b'A6_TOUCH_N42_CAL_V1', b'A6_TOUCH_N42_REPORT_PROBE_V1',
               b'upload-and-calibrate-n42', b'e3_first='):
    assert linked.count(marker) == 1, marker
for marker in (b'report_id=%02x length=%u result=%d first16=', b'e2_attempts='):
    assert linked.count(marker) == 1, marker
if args.frames:
    assert linked.count(b'A6_TOUCH_FRAME_CAPTURE_V1') == 1
    assert linked.count(b'a6_touch_frames') == 1
if args.native:
    assert linked.count(b'A6_NATIVE_INPUT_V1') == 1
    assert linked.count(b'A6 N42 native touchscreen') == 1
# The build restores generated kernel sources afterwards. Validate the linked
# opt-in metadata status and five-write ACK storage instead. Packet construction
# is independently checked by the existing compiled C packet test.
symbols = subprocess.check_output(['llvm-nm', '-S', str(build / 'vmlinux')], text=True)
ack = [line.split() for line in symbols.splitlines() if line.endswith(' a6_post_write_ack')]
assert len(ack) == 1 and int(ack[0][1], 16) == 10
subprocess.run(['python3', str(ROOT / 'scripts/test-a6-touch-post-packets.py')],
               check=True, stdout=subprocess.DEVNULL)
artifacts = {}
for suffix in ('.img3', '.raw'):
    path = ROOT / ('build/arm/a6-linux-' + KIND + suffix)
    blob = path.read_bytes()
    artifacts[path.name] = {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
print(json.dumps({'status': 'static checks passed; not booted', 'artifacts': artifacts}, indent=2))

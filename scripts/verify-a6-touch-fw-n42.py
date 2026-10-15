#!/usr/bin/env python3
"""Verify the fixed N42 RAM-upload image and its stock-code provenance."""
import hashlib
import json
from pathlib import Path
import plistlib
import re
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / 'build/touch-research'
KIND = sys.argv[1] if len(sys.argv) > 1 else 'touch-fw-n42'
assert KIND in ('touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42')
BUILD = ROOT / ('build/linux-a6-' + KIND)
ARM = ROOT / 'build/arm'
SOURCE_HASH = '132c013a1a19b0c6cb5ef2faf9cf0573ee9f9f429379b4912c095f4a8914a0fb'
KEXT_HASH = 'bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0'
PACKET_HASH = 'af78e1a4033c213747c2e76f7b55e38bfdc4b1f1590a6ab0b07f7fc5ff9420c3'


def digest(data):
    return hashlib.sha256(data).hexdigest()


source = (RESEARCH / 'N42.mtprops').read_bytes()
assert digest(source) == SOURCE_HASH
entry = plistlib.loads(source)['C1F57,1']
assert entry['PreconstructedBootloadPacketType'] == 'Z2'
assert isinstance(entry['Constructed Firmware'], bytes)
assert not isinstance(entry['Constructed Firmware'], list)
packet = entry['Constructed Firmware']
assert len(packet) == 64340 and digest(packet) == PACKET_HASH
assert (RESEARCH / 'N42-constructed-firmware.bin').read_bytes() == packet
if KIND in ('touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    prelink = json.loads((RESEARCH / 'ios10-touch-prelink.json').read_text())
    n42 = next(item for item in prelink
               if item.get('CFBundleName') == 'AppleMultitouchSPIC1F57')
    personality = n42['IOKitPersonalities']['AppleMultitouchSPI - C1,N41']
    assert personality['IONameMatch'] == ['multi-touch,n41']
    assert [personality[key] for key in
            ('cal-dl-addr', 'prox-cal-addr', 'fw-execute-addr')] == [
        0x10009000, 0x10009600, 0x10003400]

kext = (RESEARCH / 'AppleMultitouchSPI-ios10.macho').read_bytes()
assert digest(kext) == KEXT_HASH
word = lambda addr: struct.unpack_from('<I', kext, addr - 0x80854000)[0]
assert word(0x80868a88 + 0x8c) == 0x8085fa55
assert word(0x80868a88 + 0x94) == 0x8085fc19
assert word(0x808684d4 + 0x524) == 0x8085de79
if KIND in ('touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    assert word(0x80868a88 + 0x88) == 0x80862451
    assert word(0x80868a88 + 0x4c) == 0x80860979
    assert [word(0x80868a88 + slot) for slot in
            (0xa4, 0xa0, 0x9c, 0x8c, 0x88, 0x4c)] == [
        0x80860709, 0x808601e5, 0x8085ff6d,
        0x8085fa55, 0x80862451, 0x80860979]
    assert kext[0x8085f836 - 0x80854000:
                0x8085f83c - 0x80854000] == bytes.fromhex('28 20 03 f0 88 f9')
    assert word(0x808684d4 + 0x538) == 0x8085e0c5
    assert word(0x80867020) == 0x80317a9d  # IOSleep, Thumb bit set
    assert [word(addr) for addr in (0x80860ed0, 0x80860edc,
                                    0x80862670, 0x80862674,
                                    0x80862680, 0x80862604)] == [
        0x16e4, 0x10001800, 0x10003000, 3, 0x1000300c, 0x10003058]
symbols = subprocess.check_output(
    ['llvm-nm', str(RESEARCH / 'Kernelcache-ios10.raw')], text=True)
assert '803d8888 S __ZN7OSArray9metaClassE' in symbols
assert '803d8b68 S __ZN6OSData9metaClassE' in symbols

linked = (BUILD / 'vmlinux').read_bytes()
assert linked.count(packet) == 1
for marker in (b'A6_TOUCH_N42_FW_V1',
               b'upload-and-calibrate-n42' if KIND in ('touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42') else b'upload-fixed-n42',
               b'a6_touch_fw_n42'):
    assert linked.count(marker) == 1, marker
if KIND in ('touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    for marker in (b'A6_TOUCH_N42_POST_V1', b'a6_touch_post_n42'):
        assert linked.count(marker) == 1, marker
    assert b'upload-fixed-n42' not in linked
    subprocess.run(['python3', str(ROOT / 'scripts/test-a6-touch-post-packets.py')],
                   check=True, stdout=subprocess.DEVNULL)
if KIND in ('touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    for marker in (b'A6_TOUCH_N42_REPORT_PROBE_V1', b'a6_touch_report_n42'):
        assert linked.count(marker) == 1, marker
if KIND in ('touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    for marker in (b'A6_TOUCH_N42_CAL_V1', b'a6_touch_cal_n42'):
        assert linked.count(marker) == 1, marker
    private_manifest = json.loads((RESEARCH / 'n42-calibration-packets.json').read_text())
    assert private_manifest['source_sha256'] == '4175acad7a056529f793feb61f7026dcea165c42fb000df51131ae89112893ba'
    assert [(item['address'], item['packet_bytes']) for item in private_manifest['packets']] == [
        ('0x10009600', 144), ('0x10009000', 1024), ('0x100093f0', 32)]
    generated = (RESEARCH / 'n42-calibration-packets.inc').read_text()
    for item in private_manifest['packets']:
        match = re.search(r'static const u8 ' + item['name'] +
                          r'\[\] = \{(.*?)\};', generated, re.S)
        assert match, item['name']
        data = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-f]{2})', match[1]))
        assert len(data) == item['packet_bytes'] and digest(data) == item['sha256']
        assert linked.count(data) == 1, item['name']
if KIND in ('touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    assert linked.count(b'e2_attempts=%u second_replies=') == 1
if KIND in ('touch-clk32-n42', 'touch-e3-info-n42'):
    symbol_lines = subprocess.check_output(['llvm-nm', '-S', str(BUILD / 'vmlinux')],
                                           text=True).splitlines()
    ack_symbols = [line.split() for line in symbol_lines
                   if line.endswith(' a6_post_write_ack')]
    assert len(ack_symbols) == 1 and int(ack_symbols[0][1], 16) == 10
    source = (ROOT / 'kernel/platform/a6-touch-post-upload.inc').read_text()
    assert 'a6_post_write(0x10003518, 1, 4, cs)' in source
if KIND == 'touch-e3-info-n42':
    assert linked.count(b'e3_first=%16phN e3_second=%16phN') == 1
    source = (ROOT / 'kernel/platform/a6-touch-report-probe.inc').read_text()
    for marker in ('request[0] = 0xe3', 'request[1] = 0xd1',
                   'a6_report_reply_valid(a6_report_e3_second, 0xe3)',
                   'a6_report_e3_length > a6_report_max_packet'):
        assert marker in source, marker
for inherited in (b'A6_CHARGER_PROOF_V1', b'A6_BATTERY_HDQ_ECHO_GUARD_V4',
                  b'A6_D1972_VBAT_ADC_V1'):
    assert linked.count(inherited) == 1, inherited

for script in ('verify-a6-touch-transport.py',
               'verify-a6-charger-vbus-adc.py',
               'verify-a6-charger-vbat-monitor.py',
               'verify-a6-charger-vbat-hdq-phase.py'):
    subprocess.run(['python3', str(ROOT / 'scripts' / script), KIND],
                   check=True, stdout=subprocess.DEVNULL)

paths = [ARM / f'a6-linux-{KIND}.img3',
         ARM / f'a6-linux-{KIND}.raw',
         ARM / f'a6-n42ap-{KIND}.dtb',
         BUILD / 'arch/arm/boot/zImage']
report = {
    'status': 'built and statically verified; not booted',
    'kind': KIND,
    'stock_kext_sha256': KEXT_HASH,
    'stock_send_slot': '0x94',
    'stock_ack_slot': '0x524',
    'packet_bytes': len(packet),
    'packet_sha256': PACKET_HASH,
    'linked_packet_copies': 1,
    'checks': ['boot image round trip', 'root-only permanent callbacks',
               'bus-powered USB descriptor', 'VBUS/VBAT/HDQ inherited'] +
              (['stock post-control vtable/defaults and exact C wire packets']
               if KIND in ('touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42') else []) +
              (['bounded E2 and frame-header probe']
               if KIND in ('touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42') else []) +
              (['bounded E2 and E3 report-info probe']
               if KIND == 'touch-e3-info-n42' else []) +
              (['private factory calibration packets and corrected N42 execute address']
               if KIND in ('touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42') else []) +
              (['four bounded E2 exchange pairs']
               if KIND in ('touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42') else []) +
              (['N42 clk32 enable fifth post-control write']
               if KIND in ('touch-clk32-n42', 'touch-e3-info-n42') else []) +
              (['two fixed E3 family-info transfers with reply and length guards']
               if KIND == 'touch-e3-info-n42' else []),
    'artifacts': {
        str(path.relative_to(ROOT)): {
            'bytes': path.stat().st_size,
            'sha256': digest(path.read_bytes()),
        } for path in paths
    },
}
print(json.dumps(report, indent=2))

#!/usr/bin/env python3
"""Extract the pinned N42 controller packet for a future RAM-only touch test."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import runpy
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'build/touch-research/N42.mtprops'
OUTPUT = ROOT / 'build/touch-research/N42-constructed-firmware.bin'
MANIFEST = ROOT / 'build/touch-research/N42-constructed-firmware.json'
SOURCE_SHA256 = '132c013a1a19b0c6cb5ef2faf9cf0573ee9f9f429379b4912c095f4a8914a0fb'
PACKET_SHA256 = 'af78e1a4033c213747c2e76f7b55e38bfdc4b1f1590a6ab0b07f7fc5ff9420c3'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_private(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.',
                                     delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    source = SOURCE.read_bytes()
    if sha256(source) != SOURCE_SHA256:
        raise ValueError('N42 mtprops source hash mismatch')
    audit = runpy.run_path(str(ROOT / 'scripts/inspect-a6-touch-firmware.py'))['inspect'](SOURCE)
    entry = plistlib.loads(source)['C1F57,1']
    packet = entry['Constructed Firmware']
    if not isinstance(packet, bytes) or len(packet) != 64340 or sha256(packet) != PACKET_SHA256:
        raise ValueError('N42 constructed packet does not match pinned bytes')
    if audit['packet_sha256'] != PACKET_SHA256 or not audit['checksums_valid']:
        raise ValueError('N42 packet integrity audit failed')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    write_private(OUTPUT, packet)
    report = {
        'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': SOURCE_SHA256,
        'packet': str(OUTPUT.relative_to(ROOT)),
        'packet_bytes': len(packet),
        'packet_sha256': PACKET_SHA256,
        'boot_packet_type': audit['boot_packet_type'],
        'stock_n42_send_slot': '0x94',
        'stock_n42_send_method': '0x8085fc18',
        'hardware_transfer': False,
    }
    write_private(MANIFEST, (json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

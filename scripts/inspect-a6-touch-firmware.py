#!/usr/bin/env python3
"""Audit an n42 stock mtprops boot packet offline; never accesses the phone."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib


def inspect(path):
    raw = path.read_bytes()
    if not 0 < len(raw) <= 1024 * 1024:
        raise ValueError('unexpected mtprops size')
    props = plistlib.loads(raw)
    entry = props['C1F57,1']
    if entry['PreconstructedBootloadPacketType'] != 'Z2':
        raise ValueError('unexpected boot packet type')
    packet = entry['Constructed Firmware']
    if not isinstance(packet, bytes) or len(packet) < 16:
        raise ValueError('missing boot packet')
    if packet[:4] != bytes.fromhex('18e13001'):
        raise ValueError('unexpected boot packet command')
    payload_size = int.from_bytes(packet[4:6], 'big') * 4
    if len(packet) != payload_size + 16:
        raise ValueError('boot packet length mismatch')
    # Legacy HBPP uses big-endian 16-bit words, low word first for u32.
    def word32(data):
        return int.from_bytes(data[:2], 'big') | (int.from_bytes(data[2:4], 'big') << 16)
    header_sum = int.from_bytes(packet[10:12], 'big')
    if header_sum != sum(packet[4:10]):
        raise ValueError('boot packet header checksum mismatch')
    payload = packet[12:-4]
    payload_sum = word32(packet[-4:])
    if payload_sum != sum(payload):
        raise ValueError('boot packet payload checksum mismatch')
    return {
        'source': str(path),
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'personality': 'C1F57,1',
        'firmware_version': entry['Constructed Firmware Version'],
        'boot_packet_type': 'Z2',
        'packet_bytes': len(packet),
        'packet_sha256': hashlib.sha256(packet).hexdigest(),
        'payload_bytes': payload_size,
        'controller_destination': hex(word32(packet[6:10])),
        'header_checksum': hex(header_sum),
        'payload_checksum': hex(payload_sum),
        'checksums_valid': True,
        'note': 'Packet integrity only; does not establish N1 runtime or A6 SPI compatibility.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mtprops', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.mtprops), indent=2))
    except (KeyError, TypeError, ValueError, plistlib.InvalidFileException) as exc:
        parser.exit(1, f'Invalid n42 firmware: {exc}\n')

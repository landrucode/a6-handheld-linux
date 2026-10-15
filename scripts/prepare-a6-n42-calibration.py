#!/usr/bin/env python3
"""Build local N42 HBPP calibration packet arrays from the private live capture."""
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'build/session-logs/a6-touch-capture-live.bin'
OUTPUT = ROOT / 'build/touch-research/n42-calibration-packets.inc'
MANIFEST = ROOT / 'build/touch-research/n42-calibration-packets.json'
EXPECTED = {
    'mtcl': (0x600, 1024, 0x10009000,
             'e9c624ef6620977d89784294b35de95eb98a1fde1e85e2ec82dd6e54d59522a4'),
    'pxcl': (0xa00, 128, 0x10009600,
             'f0f32048e66d3a793e887d958831e7fe8ff146494337a234dd59576a5aa51925'),
}
EXPECTED_PACKET_HASHES = {
    'a6_n42_pxcl_0': 'd2b190523ae277676120f5bd376dc79198f26cd51dff4fd423dc1fec6be34e7e',
    'a6_n42_mtcl_0': 'e57249368db9e72cc69939b2af7e4d9ba0b815f8bf2371a3e8c499743b865001',
    'a6_n42_mtcl_1': '694bccd5d75760fde575e5fa8c838f1e3f7cacc26f5a43c373e0000ba2b10473',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def be16(value):
    return value.to_bytes(2, 'big')


def word(value):
    return be16(value & 0xffff) + be16(value >> 16)


def packet(address, payload):
    assert len(payload) <= 0x3f0 and len(payload) % 4 == 0
    header = b'\x30\x01' + be16(len(payload) // 4) + word(address)
    header += be16(sum(header[2:]) & 0xffff)
    wire_data = b''.join(payload[i + 1:i + 2] + payload[i:i + 1] +
                         payload[i + 3:i + 4] + payload[i + 2:i + 3]
                         for i in range(0, len(payload), 4))
    result = b'\x18\xe1' + header + wire_data + word(sum(wire_data) & 0xffffffff)
    assert len(result) == len(payload) + 16
    return result


def main():
    capture = CAPTURE.read_bytes()
    assert len(capture) == 2816, 'capture length changed'
    assert sha(capture) == '4175acad7a056529f793feb61f7026dcea165c42fb000df51131ae89112893ba'
    arrays = {}
    report = {'source': str(CAPTURE.relative_to(ROOT)), 'source_sha256': sha(capture),
              'packets': []}
    # Stock slot a0 uses prox address; slot 9c uses touch address.
    for name in ('pxcl', 'mtcl'):
        offset, length, address, expected_hash = EXPECTED[name]
        data = capture[offset:offset + length]
        assert len(data) == length and sha(data) == expected_hash
        for index, start in enumerate(range(0, length, 0x3f0)):
            chunk = data[start:start + 0x3f0]
            key = f'a6_n42_{name}_{index}'
            arrays[key] = packet(address + start, chunk)
            assert sha(arrays[key]) == EXPECTED_PACKET_HASHES[key], key
            report['packets'].append({'name': key, 'address': hex(address + start),
                                      'payload_bytes': len(chunk),
                                      'packet_bytes': len(arrays[key]),
                                      'sha256': sha(arrays[key])})
    lines = ['/* Private N42 factory calibration; generated locally, never commit. */']
    for key, value in arrays.items():
        lines.append(f'static const u8 {key}[] = {{')
        for offset in range(0, len(value), 16):
            lines.append('\t' + ', '.join(f'0x{x:02x}' for x in value[offset:offset + 16]) + ',')
        lines.append('};')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write('\n'.join(lines) + '\n')
    os.chmod(OUTPUT, 0o600)
    fd = os.open(MANIFEST, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    os.chmod(MANIFEST, 0o600)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

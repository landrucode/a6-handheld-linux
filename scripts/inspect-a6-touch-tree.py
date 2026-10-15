#!/usr/bin/env python3
"""Read-only inventory of the n42 Apple device tree; no phone/MMIO access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('tree', type=Path)
args = parser.parse_args()
data = args.tree.read_bytes()
if not 8 <= len(data) <= 1024 * 1024:
    parser.error('unexpected tree size')
nodes = []
def parse(offset, parent, depth=0):
    if depth > 32 or offset + 8 > len(data):
        raise ValueError('invalid node bounds')
    count, children = struct.unpack_from('<II', data, offset)
    offset += 8
    if count > 1024 or children > 1024:
        raise ValueError('invalid node counts')
    props = {}
    for _ in range(count):
        if offset + 36 > len(data):
            raise ValueError('truncated property')
        key = data[offset:offset+32].split(b'\0', 1)[0].decode('ascii')
        length = struct.unpack_from('<I', data, offset+32)[0] & 0x7fffffff
        offset += 36
        if offset + length > len(data) or key in props:
            raise ValueError('invalid property bounds or duplicate')
        props[key] = data[offset:offset+length]
        offset += (length + 3) & ~3
    name = props.get('name', b'?').split(b'\0', 1)[0].decode('ascii')
    path = parent + '/' + name
    if name in ('arm-io', 'gpio', 'spi1', 'multi-touch', 'spi3', 'audio-codec', 'pwm', 'grape-clk', 'i2c0', 'pmu'):
        decoded = {}
        for key, value in props.items():
            if 'calibration' in key:
                decoded[key] = {'bytes': len(value), 'nonzero_bytes': sum(x != 0 for x in value), 'sha256': hashlib.sha256(value).hexdigest()}
                if value.startswith(b'syscfg/') and value.endswith(b'\0'):
                    decoded[key]['kind'] = 'syscfg-reference-not-calibration'
                    decoded[key]['reference'] = value[:-1].decode('ascii')
                else:
                    decoded[key]['kind'] = 'calibration-bytes'
            elif key in ('name', 'compatible', 'device_type'):
                decoded[key] = value.rstrip(b'\0').decode('ascii')
            elif len(value) <= 128:
                decoded[key] = {'hex': value.hex(), 'le32': list(struct.unpack('<'+'I'*(len(value)//4), value)) if len(value)%4 == 0 else None}
        nodes.append({'path': path, 'properties': decoded})
    for _ in range(children):
        offset = parse(offset, path, depth+1)
    return offset
end = parse(0, '')
if end != len(data):
    raise ValueError('trailing bytes')
print(json.dumps({'source_sha256': hashlib.sha256(data).hexdigest(), 'parsed_bytes': end, 'nodes': nodes}, indent=2))

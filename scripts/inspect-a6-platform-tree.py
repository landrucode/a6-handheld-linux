#!/usr/bin/env python3
"""Inventory selected stock platform nodes offline; never access phone/MMIO."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def parse_tree(data):
    nodes = {}
    def walk(offset, parent, depth):
        if depth > 32 or offset + 8 > len(data):
            raise ValueError('node bounds')
        count, children = struct.unpack_from('<II', data, offset)
        offset += 8
        if count > 1024 or children > 1024:
            raise ValueError('node count')
        props = {}
        for _ in range(count):
            if offset + 36 > len(data):
                raise ValueError('property bounds')
            key = data[offset:offset+32].split(b'\0',1)[0].decode('ascii')
            size = struct.unpack_from('<I', data, offset+32)[0] & 0x7fffffff
            offset += 36
            if offset + size > len(data) or key in props:
                raise ValueError('property size/duplicate')
            props[key] = data[offset:offset+size]
            offset += (size + 3) & ~3
        path = parent + '/' + props.get('name', b'?').split(b'\0',1)[0].decode('ascii')
        if path in nodes:
            raise ValueError('duplicate node')
        nodes[path] = props
        for _ in range(children):
            offset = walk(offset, path, depth+1)
        return offset
    if walk(0, '', 0) != len(data):
        raise ValueError('trailing bytes')
    return nodes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('tree', type=Path)
    p.add_argument('--paths', action='store_true', help='show paths only')
    a = p.parse_args()
    data = a.tree.read_bytes()
    if not 8 <= len(data) <= 1048576:
        p.error('unexpected tree size')
    nodes = parse_tree(data)
    if a.paths:
        print('\n'.join(nodes)); return
    chosen = {}
    allowed = {'name','compatible','device_type','reg','ranges','clock-gates','clock-ids',
               'interrupts','interrupt-parent','AAPL,phandle','gpio-pin-config',
               'power-gates','max-brightness','dwi-version'}
    for path, props in nodes.items():
        if not re.search(r'(arm-io$|backlight|/dwi$|vibr|motor|accel|gyro|lis|lsm|pwm|i2c)',path,re.I):
            continue
        selected = {}
        for key, value in props.items():
            if key not in allowed and not key.startswith(('function-', 'power_')):
                continue
            if key in ('name','compatible','device_type'):
                selected[key] = value.rstrip(b'\0').decode('ascii')
            else:
                selected[key] = {'hex':value.hex(), 'le32':list(struct.unpack('<'+'I'*(len(value)//4),value)) if len(value)%4==0 else None}
        chosen[path] = selected
    print(json.dumps({'source_sha256':hashlib.sha256(data).hexdigest(),'nodes':chosen},indent=2))


if __name__ == '__main__':
    main()

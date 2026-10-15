#!/usr/bin/env python3
"""Extract hardware-platform kexts/metadata from a local ARM32 stock kernelcache.

Input must already be unpacked. Outputs are host research artifacts only.
Analysis copies omit orphaned LC_DYSYMTAB commands for llvm-objdump; originals
are retained byte-for-byte and neither form is intended for booting.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET


def commands(data):
    if len(data) < 28 or struct.unpack_from('<I', data)[0] != 0xfeedface:
        raise ValueError('expected little-endian ARM32 Mach-O')
    if struct.unpack_from('<I', data, 4)[0] != 12:
        raise ValueError('expected ARM CPU type')
    count, size = struct.unpack_from('<II', data, 16)
    if count > 4096 or size > len(data) - 28:
        raise ValueError('invalid load-command table')
    offset = 28
    for _ in range(count):
        if offset + 8 > 28 + size:
            raise ValueError('truncated load command')
        kind, length = struct.unpack_from('<II', data, offset)
        if length < 8 or offset + length > 28 + size:
            raise ValueError('invalid load-command size')
        yield kind, data[offset:offset + length]
        offset += length
    if offset != 28 + size:
        raise ValueError('load-command size mismatch')


def extract(source, output, match=None):
    if not 28 <= source.stat().st_size <= 128 * 1024 * 1024:
        raise ValueError('unexpected kernelcache size')
    data = source.read_bytes()
    segments = {}
    for kind, command in commands(data):
        if kind == 1:
            if len(command) < 56:
                raise ValueError('short segment command')
            name = command[8:24].rstrip(b'\0').decode('ascii')
            segments[name] = struct.unpack_from('<IIII', command, 24)
    _, _, offset, size = segments['__PRELINK_INFO']
    if offset + size > len(data):
        raise ValueError('prelink metadata outside file')
    root = ET.fromstring(data[offset:offset + size].rstrip(b'\0'))
    ids = {e.attrib['ID']: e for e in root.iter() if 'ID' in e.attrib}

    def decode(e, depth=0):
        if depth > 128:
            raise ValueError('recursive prelink metadata')
        if 'IDREF' in e.attrib:
            return decode(ids[e.attrib['IDREF']], depth + 1)
        if e.tag == 'dict':
            children = list(e)
            if len(children) % 2 or any(c.tag != 'key' for c in children[::2]):
                raise ValueError('malformed dictionary')
            return {children[i].text: decode(children[i + 1], depth + 1)
                    for i in range(0, len(children), 2)}
        if e.tag == 'array':
            return [decode(c, depth + 1) for c in e]
        if e.tag == 'integer':
            return int(e.text or '0', 0)
        if e.tag in ('true', 'false'):
            return e.tag == 'true'
        return e.text

    info = decode(root if root.tag == 'dict' else root[0])
    def selected_bundle(entry):
        name = entry.get('CFBundleIdentifier', '')
        if match:
            return any(token in name for token in match)
        return (any(token in name for token in
                    ('Multitouch', 'SamsungSPI', 'AppleS5L8930X', 'AppleS5L8950X',
                     'PWM', 'PMU', 'I2C', 'AppleARMPlatform', 'TriStar',
                     'LMBacklight', 'AppleS5L8940XDWI', 'AppleInterruptController'))
                and not any(token in name for token in ('USB', 'DART')))

    selected = [entry for entry in info['_PrelinkInfoDictionary']
                if selected_bundle(entry)]
    output.mkdir(parents=True, exist_ok=True)
    (output / 'prelink.json').write_text(json.dumps(selected, indent=2) + '\n')
    manifest = {'source_sha256': hashlib.sha256(data).hexdigest(), 'kexts': []}
    for entry in selected:
        size = entry.get('_PrelinkExecutableSize', 0)
        if not size:
            continue
        addr = entry['_PrelinkExecutableLoadAddr']
        segment = next(s for s in segments.values() if s[0] <= addr and addr + size <= s[0] + s[3])
        offset = segment[2] + addr - segment[0]
        if offset + size > len(data):
            raise ValueError('kext outside input')
        original = data[offset:offset + size]
        name = entry['CFBundleIdentifier']
        if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for c in name):
            raise ValueError('unsafe bundle filename')
        (output / (name + '.macho')).write_bytes(original)
        parsed = list(commands(original))
        kept = [c for kind, c in parsed if kind != 0xb]
        rewritten = b''.join(kept)
        old_size = struct.unpack_from('<I', original, 20)[0]
        analysis = bytearray(original)
        struct.pack_into('<II', analysis, 16, len(kept), len(rewritten))
        analysis[28:28 + old_size] = rewritten + bytes(old_size - len(rewritten))
        (output / (name + '-analysis.macho')).write_bytes(analysis)
        manifest['kexts'].append({'bundle': name, 'vm_address': hex(addr),
                                 'file_offset': hex(offset), 'bytes': size,
                                 'sha256': hashlib.sha256(original).hexdigest()})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernelcache', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--match', action='append', help='Opt-in bundle substring; repeat for multiple selectors')
    args = parser.parse_args()
    extract(args.kernelcache, args.output, args.match)

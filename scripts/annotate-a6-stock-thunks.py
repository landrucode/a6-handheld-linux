#!/usr/bin/env python3
"""Resolve ARM Thumb import thunks against the pinned local stock kernel.

Input and annotated disassembly remain under ignored build/. No device access.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SHA = 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disassembly', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source, output = args.disassembly.resolve(), args.output.resolve()
    for path in (source, output):
        if not path.is_relative_to(ROOT / 'build'):
            raise ValueError('keep proprietary research under ignored build/')
    if output.exists():
        raise ValueError('preserve previous output; choose a new filename')
    kernel = ROOT / 'build/touch-research/Kernelcache-ios10.raw'
    data = kernel.read_bytes()
    if hashlib.sha256(data).hexdigest() != KERNEL_SHA:
        raise ValueError('stock kernel checksum mismatch')
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'scripts/extract-a6-stock-touch.py')
    extract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extract)
    segments = [struct.unpack_from('<IIII', command, 24)
                for kind, command in extract.commands(data) if kind == 1]

    def word(address):
        for base, _, offset, size in segments:
            if base <= address and address + 4 <= base + size:
                return struct.unpack_from('<I', data, offset + address - base)[0]
        raise ValueError('thunk pointer outside file-backed kernel segments')

    nm = subprocess.check_output(['llvm-nm', '--demangle', str(kernel)], text=True)
    symbols = {}
    for line in nm.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) == 3 and re.fullmatch(r'[0-9a-fA-F]+', fields[0]):
            symbols[int(fields[0], 16) & ~1] = fields[2]
    lines = source.read_text().splitlines()
    resolved = {}
    for index, line in enumerate(lines[:-4]):
        low = re.match(r'([0-9a-f]+):.*movw\s+r12, #0x([0-9a-f]+)', line)
        high = re.search(r'movt\s+r12, #0x([0-9a-f]+)', lines[index + 1])
        pc = re.match(r'([0-9a-f]+):.*add\s+r12, pc', lines[index + 2])
        load = re.search(r'ldr\.w\s+r12, \[r12\]', lines[index + 3])
        branch = re.search(r'\bbx\s+r12\b', lines[index + 4])
        if not all((low, high, pc, load, branch)):
            continue
        address = int(pc[1], 16) + 4 + int(low[2], 16) + (int(high[1], 16) << 16)
        target = word(address) & ~1
        resolved[int(low[1], 16)] = symbols.get(target, hex(target))
    count = 0
    for index, line in enumerate(lines):
        call = re.search(r'\b(?:bl|b\.w)\s+0x([0-9a-f]+)', line)
        if call and int(call[1], 16) in resolved:
            lines[index] += ' ; ' + resolved[int(call[1], 16)]
            count += 1
    if not resolved or not count:
        raise ValueError('no resolved imports/calls; check Thumb disassembly')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines) + '\n')
    print(f'{len(resolved)} import thunks; {count} annotated calls; output: {output.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

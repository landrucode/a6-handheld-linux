#!/usr/bin/env python3
"""Index direct stock MCA register-helper calls from a local analysis Mach-O.

Offline only. This reports local literal arguments, not a register specification
or executable recipe. Computed values, predicated values and values across
branches/calls are deliberately left unresolved. No proprietary bytes emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def inspect(path):
    data = path.read_bytes()
    if not 28 <= len(data) <= 1024 * 1024:
        raise ValueError('unexpected analysis image size')
    if hashlib.sha256(data).hexdigest() != '221b5a08896281dc20729783e1c265e40a7c6e70756b3c1599447fefbce6ae72':
        raise ValueError('expected extracted 14G61 AppleAE2Audio analysis image')
    result = subprocess.run(['llvm-objdump', '-d', '--triple=thumbv7-apple-ios', str(path)],
                            capture_output=True, text=True, check=True, timeout=30)
    instructions = []
    for line in result.stdout.splitlines():
        match = re.match(r'^([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+\s*([a-z][a-z0-9.]*)\s*(.*?)\s*(?:@.*)?$', line)
        if match:
            instructions.append((int(match[1], 16), match[2], match[3].split('@')[0].strip()))
    targets = set()
    for _, op, operands in instructions:
        if op.startswith('b') or op.startswith('cb'):
            match = re.search(r'0x([0-9a-f]+)', operands)
            if match:
                targets.add(int(match[1], 16))

    def literal(index, register):
        # A conservative local slice; do not carry caller-saved values over calls.
        window = instructions[max(0, index - 8):index]
        if any(op.startswith('it') for _, op, _ in window):
            return None
        for position in range(index - 1, max(-1, index - 9), -1):
            address, op, operands = instructions[position]
            if instructions[position + 1][0] in targets:
                return None
            if op.startswith('b') or op.startswith('cb') or op in ('pop', 'push'):
                return None
            # Stores/tests do not define their first operand.
            if op.startswith(('str', 'cmp', 'tst', 'stm')):
                continue
            if operands.split(',', 1)[0].strip() == register:
                match = re.fullmatch(register + r', #(0x[0-9a-f]+|[0-9]+)', operands)
                if op in ('movs', 'mov', 'mov.w', 'movw') and match:
                    return {'value': int(match[1], 0), 'instruction': hex(address)}
                return None
            if op.startswith(('ldm', 'ldrd')):
                return None
        return None

    calls = []
    for index, (address, op, operands) in enumerate(instructions):
        if op not in ('bl', 'b.w'):
            continue
        target = operands.split()[0] if operands else ''
        if target not in ('0x810c15c4', '0x810c1618'):
            continue
        reg = literal(index, 'r1')
        write = target == '0x810c1618'
        calls.append({'instruction': hex(address), 'operation': 'write' if write else 'read',
                      'local_index': reg,
                      'byte_offset': hex(reg['value'] * 4) if reg else None,
                      'local_write_value': literal(index, 'r2') if write else None})
    if not calls:
        raise ValueError('no expected MCA helper calls; inspect image/build manually')
    return {'analysis_image_sha256': hashlib.sha256(data).hexdigest(),
            'scope': 'direct calls only; local literals are not proof of runtime revision or semantics',
            'calls': calls}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.image), indent=2))


if __name__ == '__main__':
    main()

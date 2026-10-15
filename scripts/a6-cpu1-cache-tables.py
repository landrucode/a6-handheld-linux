#!/usr/bin/env python3
"""Emit the offline private CPU1 WB cache table; never install it on a phone."""
from __future__ import annotations

import argparse
import hashlib
import runpy
import struct
from pathlib import Path


HERE = Path(__file__).resolve().parent
TLBI = runpy.run_path(str(HERE / 'a6-cpu1-tlbi-tables.py'))
TEST_PTES = {
    'writeback': 0x83FF683E,  # TEX=000,C=B=1: WB, read allocate.
    'writealloc': 0x83FF687E,  # TEX=001,C=B=1: WB, write allocate.
}


def table(policy: str = 'writeback', tre: bool = False,
          shared: bool = False) -> tuple[bytes, bytes]:
    l1, original = TLBI['tables']()
    TLBI['validate'](l1, original)
    l1_entries = list(struct.unpack('<4096I', l1))
    entries = list(struct.unpack('<768I', original))
    entries[0] = TEST_PTES[policy]
    if shared:
        assert tre, 'shareable profile requires checked TEX remap'
        entries[0] |= 0x400
    entries[256 + 0xF6] = 0  # No CPU1 NC identity alias of cache test page.
    entries[256 + 0xF7] = 0  # Keep the second data page unused as well.
    if tre:
        l1_entries[0x3F2] = 0x3F211C12  # Device, S=1, XN under pinned PRRR.
        for index in range(0xF8, 0xFF):
            entries[256 + index] = 0x83F00000 + index * 0x1000 + 0x36
        entries[512:514] = [0x80000036, 0x80001036]
    assert entries[0] & 0x800  # non-global
    assert bool(entries[0] & 0x400) == shared
    assert entries[0] & 0x30 == 0x30  # AP full access
    assert entries[0] & 0xC == 0xC  # C=B=1 under SCTLR.TRE=0
    assert entries[0] & 0x40 == (0x40 if policy == 'writealloc' else 0)
    assert entries[0] & 0x3 == 0x2  # small-page descriptor
    assert {i for i, value in enumerate(entries[256:512]) if value} == set(range(0xF8, 0xFF))
    assert entries[512:514] == ([0x80000036, 0x80001036] if tre else
                                [0x80000072, 0x80001072])
    assert all(value == 0 for value in entries[1:256])
    assert all(value == 0 for value in entries[514:])
    assert l1_entries[0x3F2] == (0x3F211C12 if tre else 0x3F200C06)
    return struct.pack('<4096I', *l1_entries), struct.pack('<768I', *entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--policy', choices=tuple(TEST_PTES), default='writeback',
                        help='must match the live CPU0 hardware PTE; default is not a hardware claim')
    parser.add_argument('--tre', action='store_true',
                        help='SCTLR.TRE=1 private NC and AIC types from pinned PRRR/NMRR')
    parser.add_argument('--shared', action='store_true',
                        help='candidate S=1 test page; requires --tre and CPU0 PTE change')
    args = parser.parse_args()
    l1, blob = table(args.policy, args.tre, args.shared)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(blob)
    print(f'{args.output} bytes={len(blob)} sha256={hashlib.sha256(blob).hexdigest()}')
    if args.tre:
        l1_dest = args.output.with_name(args.output.stem + '-l1.bin')
        l1_dest.write_bytes(l1)
        print(f'{l1_dest} bytes={len(l1)} sha256={hashlib.sha256(l1).hexdigest()}')
    print(f'PASS private {args.policy} test VA; TEX remap={int(args.tre)}; shared={int(args.shared)}; no CPU1 identity alias of cache data; offline only')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Emit candidate ARMv7 short-descriptor CPU1 tables, for offline review only.

No phone access and no installation. The table layout is isolated to the
explicitly reserved pages in a6-n42ap-cpu1-tlbi-probe.dts. A future guarded
image must verify all bytes before using either table.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

L1_PA = 0x83FF8000
L2_PA = 0x83FFC000
L2_IDENTITY_PA = 0x83FFC400
L2_LOW_PA = 0x83FFC800
DATA_A_PA = 0x83FF6000
DATA_B_PA = 0x83FF7000
TEST_VA = 0xC0000000
# ARM DDI 0406C.d Table B3-10: TEX=001,C=B=0 is Normal noncacheable.
# Section descriptor: AP[1:0]=11, domain 0, type=10, TEX=001.
NORMAL_NC_SECTION = 0x1C02
# Section descriptor: AP[1:0]=11, domain 0, type=10, TEX=000,B=1.
SHAREABLE_DEVICE_SECTION = 0x0C06
# Small page: AP[1:0]=11, TEX=001,C=B=0, type=10.
NORMAL_NC_SMALL_PAGE = 0x72
NON_GLOBAL = 0x800


def tables() -> tuple[bytes, bytes]:
    l1 = [0] * 4096
    l1[0x000] = L2_LOW_PA | 0x1  # only the two reserved low pages
    l1[0x3F2] = 0x3F200000 | SHAREABLE_DEVICE_SECTION  # AIC local window
    l1[0x83F] = L2_IDENTITY_PA | 0x1  # only the nine owned pages
    l1[TEST_VA >> 20] = L2_PA | 0x1  # domain-0 coarse L2 table
    l2 = [0] * 768
    l2[0] = DATA_A_PA | NORMAL_NC_SMALL_PAGE | NON_GLOBAL
    for index in range(0xF6, 0xFF):
        l2[256 + index] = 0x83F00000 + index * 0x1000 | NORMAL_NC_SMALL_PAGE
    l2[512] = 0x80000000 | NORMAL_NC_SMALL_PAGE
    l2[513] = 0x80001000 | NORMAL_NC_SMALL_PAGE
    return struct.pack('<4096I', *l1), struct.pack('<768I', *l2)


def validate(l1: bytes, l2: bytes) -> None:
    assert len(l1) == 0x4000 and L1_PA % 0x4000 == 0
    assert len(l2) == 0xc00 and all(base % 0x400 == 0 for base in (L2_PA, L2_IDENTITY_PA, L2_LOW_PA))
    words = struct.unpack('<4096I', l1)
    assert {i for i, word in enumerate(words) if word} == {0, 0x3F2, 0x83F, 0xC00}
    assert words[0] == 0x83FFC801
    assert words[0x3F2] == 0x3F200C06
    assert words[0x83F] == 0x83FFC401
    assert words[0xC00] == 0x83FFC001
    small = struct.unpack('<768I', l2)
    assert small[0] == 0x83FF6872 and all(word == 0 for word in small[1:256])
    assert {i for i, word in enumerate(small[256:512]) if word} == set(range(0xF6, 0xFF))
    assert [small[512], small[513]] == [0x80000072, 0x80001072]
    assert all(word == 0 for word in small[514:])
    assert DATA_B_PA | NORMAL_NC_SMALL_PAGE | NON_GLOBAL == 0x83FF7872


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    l1, l2 = tables()
    validate(l1, l2)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [('cpu1-l1.bin', l1), ('cpu1-l2.bin', l2)]:
        dest = args.output_dir / name
        dest.write_bytes(data)
        print(f'{dest} bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}')
    print('PASS isolated identity+AIC+one test-VA table geometry; offline only')


if __name__ == '__main__':
    main()

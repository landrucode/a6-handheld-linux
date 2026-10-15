#!/usr/bin/env python3
"""Emit checked private ARM words from the standalone MMU/IRQ object."""
import struct
import sys
from pathlib import Path
raw = Path(sys.argv[1]).read_bytes()
if not raw or len(raw) > 4096 or len(raw) % 4:
    raise ValueError('extended stub must fit private 4-KiB page')
words = struct.unpack(f'<{len(raw)//4}I', raw)
if 0x83ffe200 not in words or 0x83ff8000 not in words or 0x3f202000 not in words:
    raise ValueError('missing marker, TTBR0 or local AIC base')
Path(sys.argv[2]).write_text('static const u32 a6_tlbi_blob[] = {\n' + '\n'.join(f'    0x{word:08x},' for word in words) + '\n};\n')
print(f'PASS {len(raw)} bytes of private MMU/IRQ code, with no relocations')

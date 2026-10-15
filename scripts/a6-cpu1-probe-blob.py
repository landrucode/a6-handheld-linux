#!/usr/bin/env python3
"""Validate the reset-safe private-page layout and emit native ARM words."""
import struct
import sys
import subprocess
from pathlib import Path
raw = Path(sys.argv[1]).read_bytes()
if not raw or len(raw) > 512 or len(raw) % 4:
    raise ValueError('probe must fit below marker at +0x200 and use whole words')
words = struct.unpack(f'<{len(raw)//4}I', raw)
if words[0] != 0xf10c00c0 or 0x83ffe200 not in words or 0xa6c10001 not in words:
    raise ValueError('unexpected interrupt mask/marker/magic contract')
Path(sys.argv[2]).write_text('static const u32 a6_entry_blob[] = {\n' + '\n'.join(f'    0x{word:08x},' for word in words) + '\n};\n')
print(f'PASS private-page stub: {len(raw)} bytes, code/marker separate, checked ARM entry')

if len(sys.argv) > 3:
    symbols = {line.split()[2]: int(line.split()[0], 16) for line in subprocess.check_output(['llvm-nm', sys.argv[3]], text=True).splitlines() if len(line.split()) == 3}
    irq = symbols.get('a6_cpu1_probe_irq', 0)
    tlbi = bool(symbols.get('a6_cpu1_tlbi_profile', 0))
    cache = bool(symbols.get('a6_cpu1_cache_profile', 0))
    if cache and not tlbi:
        raise ValueError('cache profile requires the private-MMU entry profile')
    if tlbi:
        if len(sys.argv) < 5:
            raise ValueError('TLBI profile requires external stub object')
        ext_symbols = {line.split()[2]: int(line.split()[0], 16) for line in subprocess.check_output(['llvm-nm', sys.argv[4]], text=True).splitlines() if len(line.split()) == 3}
        irq = 0x83ffd000 + ext_symbols['a6_cpu1_tlbi_irq']
        abort = 0x83ffd000 + ext_symbols['a6_cpu1_tlbi_abort']
    park = symbols['a6_cpu1_probe_park']
    if not 0 <= park < len(raw) or (irq and not tlbi and not 0 < irq < len(raw)) or park % 4 or irq % 4:
        raise ValueError('invalid private vector targets')
    with Path(sys.argv[2]).open('a') as stream:
        stream.write(f'#define A6_ENTRY_TLBI_PROBE {int(tlbi)}\n')
        stream.write(f'#define A6_ENTRY_CACHE_PROBE {int(cache)}\n')
        stream.write(f'#define A6_ENTRY_ABORT_PA 0x{abort if tlbi else 0:08x}\n')
        stream.write(f'#define A6_ENTRY_FIXED_VECTORS {int(bool(symbols.get("a6_cpu1_fixed_vectors", 0)))}\n')
        stream.write(f'#define A6_ENTRY_EXPECTED_STAGE {3 if irq else 2}\n')
        stream.write(f'#define A6_ENTRY_IRQ_PA 0x{irq if tlbi else 0x83ffe000 + irq if irq else 0:08x}\n')
        stream.write(f'#define A6_ENTRY_PARK_PA 0x{0x83ffe000 + park:08x}\n')

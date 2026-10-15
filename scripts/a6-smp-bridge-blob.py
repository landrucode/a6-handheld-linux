#!/usr/bin/env python3
"""Validate the owned ARM bridge and emit its checked physical layout."""
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

obj, raw_path, destination = map(Path, sys.argv[1:])
relocations = subprocess.check_output(["llvm-readelf", "-r", str(obj)], text=True)
if "R_ARM" in relocations:
    raise SystemExit("unresolved bridge relocation")
raw = raw_path.read_bytes()
if not raw or len(raw) > 512 or len(raw) % 4:
    raise SystemExit("bridge overlaps markers or has partial instruction words")
words = struct.unpack(f"<{len(raw) // 4}I", raw)
if words[0] != 0xf10c00c0 or 0x83ffe200 not in words or 0xa6c20001 not in words:
    raise SystemExit("bridge entry/marker contract changed")
symbols = {}
for line in subprocess.check_output(["llvm-nm", str(obj)], text=True).splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
if symbols.get("a6_smp_bridge") != 0:
    raise SystemExit("bridge entry is not its first byte")
exception = symbols["a6_smp_bridge_exception"]
park = symbols["a6_smp_bridge_park"]
if not (0 < park < exception < len(raw)) or park % 4 or exception % 4:
    raise SystemExit("invalid bridge park/exception addresses")
destination.write_text(
    "/* Generated from the owned bridge; never Apple firmware. */\n"
    f"#define A6_SMP_EXCEPTION_PA 0x{0x83ffe000 + exception:08x}\n"
    f"#define A6_SMP_PARK_PA 0x{0x83ffe000 + park:08x}\n"
    "static const u32 a6_smp_bridge_blob[] = {\n" +
    "\n".join(f"\t0x{word:08x}," for word in words) + "\n};\n"
)
print(f"PASS owned bridge: {len(raw)} bytes, SHA256 {hashlib.sha256(raw).hexdigest()}")

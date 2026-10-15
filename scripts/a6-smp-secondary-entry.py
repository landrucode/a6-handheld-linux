#!/usr/bin/env python3
"""Resolve the MMU-off ARM entry for one exact A6 SMP vmlinux build."""

import argparse
import json
import re
import struct
from pathlib import Path


def symbol_addresses(path: Path) -> dict[str, int]:
    symbols = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in {
            "_text", "secondary_startup_arm", "secondary_startup",
            "__secondary_switched",
        }:
            if fields[2] in symbols:
                raise ValueError(f"duplicate symbol {fields[2]}")
            symbols[fields[2]] = int(fields[0], 16)
    if len(symbols) != 4:
        raise ValueError(f"missing entry symbol: {symbols}")
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--dram-base", default="0x80000000")
    args = parser.parse_args()
    root = args.output_root
    config = (root / ".config").read_text()
    for required in (
        "CONFIG_SMP=y", "CONFIG_NR_CPUS=2", "CONFIG_THUMB2_KERNEL=y",
        "# CONFIG_HOTPLUG_CPU is not set", "# CONFIG_CPU_IDLE is not set",
    ):
        if required not in config.splitlines():
            raise ValueError(f"required config absent: {required}")
    match = re.search(r"^CONFIG_PAGE_OFFSET=(0x[0-9A-Fa-f]+)$", config, re.M)
    if not match:
        raise ValueError("CONFIG_PAGE_OFFSET missing")
    page_offset = int(match.group(1), 16)
    dram_base = int(args.dram_base, 0)
    if dram_base != 0x80000000 or page_offset != 0xC0000000:
        raise ValueError("unreviewed N42 virtual/physical mapping")
    symbols = symbol_addresses(root / "System.map")
    arm = symbols["secondary_startup_arm"]
    thumb = symbols["secondary_startup"]
    switched = symbols["__secondary_switched"]
    if not (symbols["_text"] <= arm < thumb < switched):
        raise ValueError("secondary entry symbol order changed")
    if thumb != arm + 8 or arm & 3 or thumb & 1:
        raise ValueError("ARM-to-Thumb veneer layout changed")
    image = (root / "arch/arm/boot/Image").read_bytes()
    offset = arm - symbols["_text"]
    if image[offset:offset + 8] != struct.pack("<II", 0xe28f9001, 0xe12fff19):
        raise ValueError("secondary ARM veneer is not add r9,pc,#1; bx r9")
    physical = dram_base + arm - page_offset
    if not (dram_base + 0x8000 <= physical < dram_base + 0x800000):
        raise ValueError("secondary entry outside packed kernel identity window")
    result = {
        "vmlinux": str((root / "vmlinux").resolve()),
        "arm_entry_virtual": f"0x{arm:08x}",
        "arm_entry_physical": f"0x{physical:08x}",
        "thumb_entry_virtual": f"0x{thumb:08x}",
        "secondary_switched_virtual": f"0x{switched:08x}",
        "dram_base": f"0x{dram_base:08x}",
        "page_offset": f"0x{page_offset:08x}",
        "cpu1_released": False,
    }
    target = root / "a6-secondary-entry.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS MMU-off ARM entry {result['arm_entry_physical']} ({target})")


if __name__ == "__main__":
    main()

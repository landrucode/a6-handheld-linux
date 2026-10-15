#!/usr/bin/env python3
"""Check the N42 kernelcache entry bytes before any CPU1 release work.

Read-only: this reports the stock secondary-entry candidate and whether a
generated Linux wrapper still contains it. It does not prove the bootloader's
CPU1 vector contract or make an image safe for SMP.
"""

import argparse
import struct
from pathlib import Path


TEXT_BASE = 0x80001000
PRIMARY = 0x800B3084
SECONDARY_TAIL = PRIMARY - 4
START_CPU = 0x800B3010
LOW_RESET_VECTOR = 0x800AF000
JUMP_SLOT = 0x800B34D8
STOCK_SECONDARY_BRANCH = 0xEA0000B5


def word(data: bytes, address: int) -> int:
    offset = address - TEXT_BASE
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"address {address:#010x} is outside the image")
    return struct.unpack_from("<I", data, offset)[0]


def inspect(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    if struct.unpack_from("<I", data)[0] != 0xFEEDFACE:
        raise ValueError(f"{path}: not an N42 Mach-O kernelcache")
    return {
        "secondary_tail": word(data, SECONDARY_TAIL),
        "start_cpu_entry": word(data, START_CPU),
        "low_reset_template": word(data, LOW_RESET_VECTOR),
        "primary_entry": word(data, PRIMARY),
        "secondary_jump_slot": word(data, JUMP_SLOT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("linux", type=Path)
    args = parser.parse_args()
    stock = inspect(args.stock)
    linux = inspect(args.linux)
    if stock["secondary_tail"] != STOCK_SECONDARY_BRANCH:
        raise ValueError("stock secondary tail differs from audited N42 image")
    if stock["start_cpu_entry"] != 0xE304E040:
        raise ValueError("stock start_cpu prologue differs from audited N42 image")
    if stock["low_reset_template"] != 0xE28FFF7E:
        raise ValueError("stock low reset vector differs from audited N42 image")
    if stock["secondary_jump_slot"] != 0:
        raise ValueError("stock secondary jump slot is not initially zero")
    for field in stock:
        print(f"{field}: stock={stock[field]:#010x} linux={linux[field]:#010x}")
    mixed = (
        linux["secondary_tail"] == stock["secondary_tail"]
        and linux["start_cpu_entry"] == stock["start_cpu_entry"]
        and linux["secondary_jump_slot"] == stock["secondary_jump_slot"]
        and linux["primary_entry"] != stock["primary_entry"]
    )
    print(f"linux_retains_stock_secondary_path={int(mixed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

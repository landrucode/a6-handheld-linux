#!/usr/bin/env python3
"""Verify the actual ARM Image has usable Apple S5L UART match data."""
import argparse
import hashlib
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
args = parser.parse_args()
image = args.image.read_bytes()
base = 0xC0008000
needle = b"apple,s5l-uart\0"
matches = []
start = 0
while (offset := image.find(needle, start)) >= 0:
    start = offset + len(needle)
    # of_device_id.compatible[128] is followed by the ARM32 data pointer.
    if image[offset + len(needle):offset + 128] != bytes(128 - len(needle)):
        continue
    pointer = struct.unpack_from("<I", image, offset + 128)[0]
    if not base <= pointer <= base + len(image) - 8:
        continue
    name, uart_type = struct.unpack_from("<II", image, pointer - base)
    expected_name = b"Apple S5L UART\0"
    if image[name - base:name - base + len(expected_name)] != expected_name:
        continue
    assert uart_type == 1, f"Unexpected Apple UART type: {uart_type}"
    matches.append((base + offset, pointer))
assert len(matches) == 1, f"Expected one populated Apple S5L match entry; found {matches}"
compatible, pointer = matches[0]
print(f"PASS: compatible {compatible:#010x}, data {pointer:#010x}, Apple S5L UART type=1")
print(f"Image SHA256: {hashlib.sha256(image).hexdigest()}")

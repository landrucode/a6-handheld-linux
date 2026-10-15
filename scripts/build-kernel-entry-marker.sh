#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source="$repo_root/.deps/legacy-ios-kit/firmware/Kernelcache.n42.raw"
stub_elf="$repo_root/build/arm/a6-kernel-marker.elf"
stub_raw="$repo_root/build/arm/a6-kernel-marker.raw"
output="$repo_root/build/arm/a6-kernel-entry-marker.raw"

[[ -s "$source" ]] || {
	echo "missing $source" >&2
	exit 1
}

mkdir -p "$repo_root/build/arm"

clang \
	--target=arm-none-eabi \
	-mcpu=swift \
	-marm \
	-ffreestanding \
	-fno-pic \
	-nostdlib \
	-c \
	-o "$stub_elf" \
	"$repo_root/boot/arm/kernel-marker.S"

llvm-objcopy -O binary "$stub_elf" "$stub_raw"

python3 - "$source" "$stub_raw" "$output" <<'PY'
from pathlib import Path
import hashlib
import struct
import sys

source = Path(sys.argv[1])
stub_path = Path(sys.argv[2])
destination = Path(sys.argv[3])
data = bytearray(source.read_bytes())
stub = stub_path.read_bytes()

magic, cputype, cpusubtype, filetype, ncmds, _, _ = struct.unpack_from(
    '<7I', data, 0
)
assert (magic, cputype, cpusubtype, filetype) == (0xfeedface, 12, 11, 2)

offset = 28
entry = None
prelink_vmaddr = None
prelink_fileoff = None
prelink_filesize = None
for _ in range(ncmds):
	cmd, cmdsize = struct.unpack_from('<2I', data, offset)
	if cmd == 1:
		name = bytes(data[offset + 8:offset + 24]).split(b'\0', 1)[0]
		vmaddr, _, fileoff, filesize = struct.unpack_from('<4I', data, offset + 24)
		if name == b'__PRELINK_TEXT':
			prelink_vmaddr = vmaddr
			prelink_fileoff = fileoff
			prelink_filesize = filesize
	if cmd == 5:
		flavor, count = struct.unpack_from('<2I', data, offset + 8)
		assert (flavor, count) == (1, 17)
		state = struct.unpack_from('<17I', data, offset + 16)
		entry = state[15]
	offset += cmdsize

assert entry == 0x800b3084, hex(entry)
assert (prelink_vmaddr, prelink_fileoff, prelink_filesize) == (
	0x80465000, 0x41d000, 0xb0a000
)

# This gap is inside the executable __PRELINK_TEXT segment and is stable in
# the pinned 12H321 kernelcache. Align the start so ARM fetches are aligned.
cave_start = 0xc7338c
cave_end = 0xc84500
assert len(stub) <= cave_end - cave_start
assert all(byte == 0 for byte in data[cave_start:cave_start + len(stub)])

cave_vmaddr = prelink_vmaddr + cave_start - prelink_fileoff
entry_offset = entry - 0x80001000
assert entry_offset == 0xb2084
branch_delta = cave_vmaddr - (entry + 8)
assert branch_delta % 4 == 0
assert -(1 << 25) <= branch_delta < (1 << 25)
branch = 0xea000000 | ((branch_delta >> 2) & 0x00ffffff)

data[cave_start:cave_start + len(stub)] = stub
struct.pack_into('<I', data, entry_offset, branch)
destination.write_bytes(data)
print(f'stub:   {stub_path} ({len(stub)} bytes)')
print(f'entry:  {entry:#x} -> {cave_vmaddr:#x}')
print(f'branch: {branch:#010x}')
print(f'cave:   file 0x{cave_start:x}, vm 0x{cave_vmaddr:x}')
print(f'output: {destination} ({len(data)} bytes)')
print(f'sha256: {hashlib.sha256(data).hexdigest()}')
PY

file "$output"

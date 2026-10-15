#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
candidate="${A6_CANDIDATE_RAW:-$repo_root/build/arm/a6-linux-kernelcache.raw}"
source_asm="$repo_root/boot/arm/zimage-entry-proof.S"
proof_object="$repo_root/build/arm/a6-zimage-entry-proof.o"
proof_elf="$repo_root/build/arm/a6-zimage-entry-proof.elf"
proof_raw="$repo_root/build/arm/a6-zimage-entry-proof.bin"
output="$repo_root/build/arm/a6-linux-zimage-entry-proof.raw"
packed_output="$repo_root/build/arm/a6-linux-zimage-entry-proof.img3"
roundtrip_output="$repo_root/build/arm/a6-linux-zimage-entry-proof.roundtrip.raw"
template="$repo_root/.deps/legacy-ios-kit/kernelcache.release.n42"
xpwntool="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/xpwntool"
kernel_iv="a037ef50ae5bf24ae2d373345b6e5be5"
kernel_key="66b8ca4f732113f54dae9de7d1713093d6c54731c06033eef94489c168a8db3a"

for command_name in clang ld.lld llvm-objcopy python3; do
	command -v "$command_name" >/dev/null || {
		echo "missing required command: $command_name" >&2
		exit 1
	}
done

[[ -s "$candidate" ]] || {
	echo "missing candidate Mach-O: $candidate" >&2
	exit 1
}
[[ -s "$template" && -x "$xpwntool" ]] || {
	echo "missing kernelcache template or xpwntool" >&2
	exit 1
}

mkdir -p "$repo_root/build/arm"

clang --target=arm-none-eabi -mcpu=swift -marm -ffreestanding -fno-pic \
	-nostdlib -c -o "$proof_object" "$source_asm"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$proof_elf" "$proof_object"
if llvm-readelf -r "$proof_elf" | grep -q 'R_ARM'; then
	echo "unresolved ARM relocation in zImage-entry proof" >&2
	exit 1
fi
llvm-objcopy -O binary "$proof_elf" "$proof_raw"

python3 - "$candidate" "$proof_raw" "$output" <<'PY'
from pathlib import Path
import hashlib
import struct
import sys

candidate = Path(sys.argv[1])
proof_path = Path(sys.argv[2])
destination = Path(sys.argv[3])
original = candidate.read_bytes()
data = bytearray(original)
proof = proof_path.read_bytes()

expected_candidate = 'dde867011c309acc8acac82678d852535a26d3edffd60a76cce226466acd115c'
actual_candidate = hashlib.sha256(original).hexdigest()
assert actual_candidate == expected_candidate, actual_candidate

magic, cputype, cpusubtype, filetype, ncmds, _, _ = struct.unpack_from(
    '<7I', data, 0
)
assert (magic, cputype, cpusubtype, filetype) == (0xfeedface, 12, 11, 2)

offset = 28
text = None
prelink = None
thread_offset = None
for _ in range(ncmds):
    command, command_size = struct.unpack_from('<2I', data, offset)
    if command == 1:
        name = bytes(data[offset + 8:offset + 24]).split(b'\0', 1)[0]
        values = struct.unpack_from('<8I', data, offset + 24)
        if name == b'__TEXT':
            text = values[:4]
        elif name == b'__PRELINK_TEXT':
            prelink = values[:4]
    elif command == 5:
        flavor, count = struct.unpack_from('<2I', data, offset + 8)
        assert (flavor, count) == (1, 17)
        thread_offset = offset + 16
    offset += command_size

assert text == (0x80001000, 0x396000, 0, 0x396000), text
assert prelink == (0x80465000, 0xb0a000, 0x41d000, 0xb0a000), prelink
assert thread_offset is not None

# Confirm that the candidate still enters the unchanged normal Linux handoff.
entry = struct.unpack_from('<I', data, thread_offset + 15 * 4)[0]
assert entry == 0x800b3084, hex(entry)
entry_offset = text[2] + entry - text[0]
entry_instruction = struct.unpack_from('<I', data, entry_offset)[0]
assert entry_instruction == 0xea3020c0, hex(entry_instruction)

zimage_source_offset = 0xff000
zimage_destination = 0x82000000
assert data[zimage_source_offset:zimage_source_offset + 28] == struct.pack(
    '<7I', *([0xe1a00000] * 7)
)

# Place the stop routine immediately after the existing handoff, in the same
# verified executable zero-filled cave.  The handoff itself is not changed.
proof_offset = 0xc73500
proof_vmaddr = prelink[0] + proof_offset - prelink[2]
assert proof_vmaddr == 0x80cbb500, hex(proof_vmaddr)
assert len(proof) <= 0x400, len(proof)
assert all(byte == 0 for byte in data[proof_offset:proof_offset + len(proof)])

branch_delta = proof_vmaddr - (zimage_destination + 8)
assert branch_delta % 4 == 0
assert -(1 << 25) <= branch_delta < (1 << 25)
branch = 0xea000000 | ((branch_delta >> 2) & 0x00ffffff)

struct.pack_into('<I', data, zimage_source_offset, branch)
data[proof_offset:proof_offset + len(proof)] = proof
destination.write_bytes(data)

changed = [i for i, (a, b) in enumerate(zip(original, data)) if a != b]
allowed = set(range(zimage_source_offset, zimage_source_offset + 4))
allowed.update(range(proof_offset, proof_offset + len(proof)))
assert changed and all(i in allowed for i in changed)
assert data[entry_offset:entry_offset + 4] == original[entry_offset:entry_offset + 4]
assert data[0xc7338c:proof_offset] == original[0xc7338c:proof_offset]

print(f'candidate: {candidate} ({len(original)} bytes)')
print(f'candidate sha256: {actual_candidate}')
print(f'Mach-O entry: {entry:#010x}, unchanged instruction {entry_instruction:#010x}')
print(f'zImage runtime entry: {zimage_destination:#010x} -> proof {proof_vmaddr:#010x}')
print(f'zImage branch: {branch:#010x}')
print(f'proof: {proof_path} ({len(proof)} bytes)')
print(f'output: {destination} ({len(data)} bytes)')
print(f'output sha256: {hashlib.sha256(data).hexdigest()}')
PY

"$xpwntool" "$output" "$packed_output" -t "$template" \
	-iv "$kernel_iv" -k "$kernel_key"
"$xpwntool" "$packed_output" "$roundtrip_output" \
	-iv "$kernel_iv" -k "$kernel_key"
cmp "$output" "$roundtrip_output"
rm -f "$roundtrip_output"

echo "verified decrypt-after-repack round trip"
sha256sum "$proof_raw" "$output" "$packed_output"

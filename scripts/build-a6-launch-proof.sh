#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
candidate="${A6_CANDIDATE_RAW:-$repo_root/build/arm/a6-linux-kernelcache.raw}"
source_asm="$repo_root/boot/arm/launch-proof.S"
proof_object="$repo_root/build/arm/a6-launch-proof.o"
proof_elf="$repo_root/build/arm/a6-launch-proof.elf"
proof_raw="$repo_root/build/arm/a6-launch-proof.bin"
output="$repo_root/build/arm/a6-linux-launch-proof.raw"
packed_output="$repo_root/build/arm/a6-linux-launch-proof.img3"
roundtrip_output="$repo_root/build/arm/a6-linux-launch-proof.roundtrip.raw"
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
	echo "unresolved ARM relocation in launch proof" >&2
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

entry = struct.unpack_from('<I', data, thread_offset + 15 * 4)[0]
assert entry == 0x800b3084, hex(entry)
entry_offset = text[2] + entry - text[0]
instruction = struct.unpack_from('<I', data, entry_offset)[0]
assert instruction >> 24 == 0xea, hex(instruction)

signed_imm24 = instruction & 0x00ffffff
if signed_imm24 & 0x00800000:
    signed_imm24 -= 1 << 24
target = (entry + 8 + (signed_imm24 << 2)) & 0xffffffff
target_offset = prelink[2] + target - prelink[0]

# The Linux candidate's entry must still target its established handoff cave.
assert target == 0x80cbb38c, hex(target)
assert target_offset == 0xc7338c, hex(target_offset)
assert len(proof) <= 0x1000, len(proof)
assert target_offset + len(proof) <= len(data)

data[target_offset:target_offset + len(proof)] = proof
destination.write_bytes(data)

changed = [i for i, (a, b) in enumerate(zip(original, data)) if a != b]
assert changed
assert min(changed) >= target_offset
assert max(changed) < target_offset + len(proof)
assert data[entry_offset:entry_offset + 4] == original[entry_offset:entry_offset + 4]
assert data[0xff000:target_offset] == original[0xff000:target_offset]

print(f'candidate: {candidate} ({len(original)} bytes)')
print(f'candidate sha256: {hashlib.sha256(original).hexdigest()}')
print(f'entry: {entry:#010x}, unchanged branch -> {target:#010x}')
print(f'proof: {proof_path} ({len(proof)} bytes)')
print(f'changed span: {min(changed):#x}..{max(changed) + 1:#x}')
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

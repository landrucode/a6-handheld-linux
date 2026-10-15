#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
candidate="${A6_CANDIDATE_RAW:-$repo_root/build/arm/a6-linux-kernelcache.raw}"
source_asm="$repo_root/boot/arm/zimage-prologue-proof.S"
trampoline_object="$repo_root/build/arm/a6-zimage-prologue-trampoline.o"
trampoline_elf="$repo_root/build/arm/a6-zimage-prologue-trampoline.elf"
trampoline_raw="$repo_root/build/arm/a6-zimage-prologue-trampoline.bin"
proof_object="$repo_root/build/arm/a6-zimage-prologue-proof.o"
proof_elf="$repo_root/build/arm/a6-zimage-prologue-proof.elf"
proof_raw="$repo_root/build/arm/a6-zimage-prologue-proof.bin"
output="$repo_root/build/arm/a6-linux-zimage-prologue-proof.raw"
packed_output="$repo_root/build/arm/a6-linux-zimage-prologue-proof.img3"
roundtrip_output="$repo_root/build/arm/a6-linux-zimage-prologue-proof.roundtrip.raw"
template="$repo_root/.deps/legacy-ios-kit/kernelcache.release.n42"
xpwntool="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/xpwntool"
kernel_iv="a037ef50ae5bf24ae2d373345b6e5be5"
kernel_key="66b8ca4f732113f54dae9de7d1713093d6c54731c06033eef94489c168a8db3a"
proof_address="0x80cbb600"

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

clang --target=arm-none-eabi -mcpu=swift -mthumb -ffreestanding -fno-pic \
	-nostdlib -DTRAMPOLINE_ONLY -DPROOF_ADDRESS="$proof_address" \
	-c -o "$trampoline_object" "$source_asm"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$trampoline_elf" "$trampoline_object"
llvm-objcopy -O binary "$trampoline_elf" "$trampoline_raw"

clang --target=arm-none-eabi -mcpu=swift -mthumb -ffreestanding -fno-pic \
	-nostdlib -c -o "$proof_object" "$source_asm"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$proof_elf" "$proof_object"
llvm-objcopy -O binary "$proof_elf" "$proof_raw"

for elf in "$trampoline_elf" "$proof_elf"; do
	if llvm-readelf -r "$elf" | grep -q 'R_ARM'; then
		echo "unresolved ARM relocation in $(basename -- "$elf")" >&2
		exit 1
	fi
done

python3 - "$candidate" "$trampoline_raw" "$proof_raw" "$output" <<'PY'
from pathlib import Path
import hashlib
import struct
import sys

candidate = Path(sys.argv[1])
trampoline_path = Path(sys.argv[2])
proof_path = Path(sys.argv[3])
destination = Path(sys.argv[4])
original = candidate.read_bytes()
data = bytearray(original)
trampoline = trampoline_path.read_bytes()
proof = proof_path.read_bytes()

expected_candidate = 'dde867011c309acc8acac82678d852535a26d3edffd60a76cce226466acd115c'
actual_candidate = hashlib.sha256(original).hexdigest()
assert actual_candidate == expected_candidate, actual_candidate
assert trampoline == bytes.fromhex('dff800f001b6cb80'), trampoline.hex()

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
assert struct.unpack_from('<I', data, entry_offset)[0] == 0xea3020c0

zimage_source_offset = 0xff000
d0_offset = zimage_source_offset + 0x48
expected_d0 = bytes.fromhex('30490f61c1f81480')
assert data[d0_offset:d0_offset + len(expected_d0)] == expected_d0

proof_offset = 0xc73600
proof_vmaddr = prelink[0] + proof_offset - prelink[2]
assert proof_vmaddr == 0x80cbb600, hex(proof_vmaddr)
assert len(proof) <= 0x400, len(proof)
assert all(byte == 0 for byte in data[proof_offset:proof_offset + len(proof)])

data[d0_offset:d0_offset + len(trampoline)] = trampoline
data[proof_offset:proof_offset + len(proof)] = proof
destination.write_bytes(data)

changed = [i for i, (a, b) in enumerate(zip(original, data)) if a != b]
allowed = set(range(d0_offset, d0_offset + len(trampoline)))
allowed.update(range(proof_offset, proof_offset + len(proof)))
assert changed and all(i in allowed for i in changed)
assert data[entry_offset:entry_offset + 4] == original[entry_offset:entry_offset + 4]
assert data[zimage_source_offset:zimage_source_offset + 0x48] == original[
    zimage_source_offset:zimage_source_offset + 0x48
]
assert data[0xc7338c:proof_offset] == original[0xc7338c:proof_offset]

print(f'candidate: {candidate} ({len(original)} bytes)')
print(f'candidate sha256: {actual_candidate}')
print(f'Mach-O entry and handoff: unchanged')
print(f'zImage D0 runtime address: {0x82000048:#010x}')
print(f'trampoline: {trampoline.hex()} -> Thumb proof {proof_vmaddr | 1:#010x}')
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
sha256sum "$trampoline_raw" "$proof_raw" "$output" "$packed_output"

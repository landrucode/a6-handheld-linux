#!/usr/bin/env bash
set -euo pipefail
echo 'Withdrawn: invalid diagnostic placement and branch targets; use the handoff/ledger return proofs.' >&2
exit 1

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
candidate="$repo_root/build/arm/a6-linux-kernelcache.raw"
trampoline_source="$repo_root/boot/arm/zimage-kernel-entry-proof.S"
proof_source="$repo_root/boot/arm/kernel-entry-proof.S"
trampoline_object="$repo_root/build/arm/a6-zimage-kernel-entry-trampoline.o"
trampoline_elf="$repo_root/build/arm/a6-zimage-kernel-entry-trampoline.elf"
trampoline_raw="$repo_root/build/arm/a6-zimage-kernel-entry-trampoline.bin"
proof_object="$repo_root/build/arm/a6-kernel-entry-proof.o"
proof_elf="$repo_root/build/arm/a6-kernel-entry-proof.elf"
proof_raw="$repo_root/build/arm/a6-kernel-entry-proof.bin"
output="$repo_root/build/arm/a6-linux-zimage-kernel-entry-proof.raw"
packed_output="$repo_root/build/arm/a6-linux-zimage-kernel-entry-proof.img3"
roundtrip_output="$repo_root/build/arm/a6-linux-zimage-kernel-entry-proof.roundtrip.raw"
template="$repo_root/.deps/legacy-ios-kit/kernelcache.release.n42"
xpwntool="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/xpwntool"
kernel_iv="a037ef50ae5bf24ae2d373345b6e5be5"
kernel_key="66b8ca4f732113f54dae9de7d1713093d6c54731c06033eef94489c168a8db3a"

for command_name in clang ld.lld llvm-objcopy llvm-readelf python3; do
	command -v "$command_name" >/dev/null || {
		echo "missing required command: $command_name" >&2
		exit 1
	}
done

[[ -s "$candidate" && -s "$template" && -x "$xpwntool" ]]
mkdir -p "$repo_root/build/arm"

proof_address=0x80cbb900
branch_delta=$((proof_address - (0x80008000 + 8)))
(( branch_delta % 4 == 0 ))
(( branch_delta >= -(1 << 25) && branch_delta < (1 << 25) ))
branch_instruction=$((0xea000000 | ((branch_delta >> 2) & 0x00ffffff)))

clang --target=arm-none-eabi -mcpu=swift -mthumb -ffreestanding -fno-pic \
	-nostdlib -DTRAMPOLINE_ONLY \
	-DBRANCH_INSTRUCTION="$branch_instruction" \
	-c -o "$trampoline_object" "$trampoline_source"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$trampoline_elf" "$trampoline_object"
if llvm-readelf -r "$trampoline_elf" | grep -q 'R_ARM'; then
	echo "unresolved ARM relocation in kernel-entry trampoline" >&2
	exit 1
fi
llvm-objcopy -O binary "$trampoline_elf" "$trampoline_raw"

clang --target=arm-none-eabi -mcpu=swift -marm -ffreestanding -fno-pic \
	-nostdlib -c -o "$proof_object" "$proof_source"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$proof_elf" "$proof_object"
if llvm-readelf -r "$proof_elf" | grep -q 'R_ARM'; then
	echo "unresolved ARM relocation in kernel-entry proof" >&2
	exit 1
fi
llvm-objcopy -O binary "$proof_elf" "$proof_raw"

python3 - "$candidate" "$trampoline_raw" "$proof_raw" "$output" <<'PY'
from pathlib import Path
import hashlib
import struct
import sys

candidate, trampoline_path, proof_path, destination = map(Path, sys.argv[1:])
original = candidate.read_bytes()
data = bytearray(original)
trampoline = trampoline_path.read_bytes()
proof = proof_path.read_bytes()

expected = 'dde867011c309acc8acac82678d852535a26d3edffd60a76cce226466acd115c'
assert hashlib.sha256(original).hexdigest() == expected
assert len(trampoline) <= 0x40, len(trampoline)
assert len(proof) <= 0x400, len(proof)

magic, cputype, cpusubtype, filetype, ncmds, _, _ = struct.unpack_from(
    '<7I', data, 0
)
assert (magic, cputype, cpusubtype, filetype) == (0xfeedface, 12, 11, 2)

offset = 28
text = prelink = None
thread_offset = None
for _ in range(ncmds):
    command, size = struct.unpack_from('<2I', data, offset)
    if command == 1:
        name = bytes(data[offset + 8:offset + 24]).split(b'\0', 1)[0]
        values = struct.unpack_from('<8I', data, offset + 24)
        if name == b'__TEXT':
            text = values[:4]
        elif name == b'__PRELINK_TEXT':
            prelink = values[:4]
    elif command == 5:
        assert struct.unpack_from('<2I', data, offset + 8) == (1, 17)
        thread_offset = offset + 16
    offset += size
assert text == (0x80001000, 0x396000, 0, 0x396000)
assert prelink == (0x80465000, 0xb0a000, 0x41d000, 0xb0a000)
assert thread_offset is not None

entry = struct.unpack_from('<I', data, thread_offset + 15 * 4)[0]
entry_offset = entry - text[0]
assert entry == 0x800b3084
assert struct.unpack_from('<I', data, entry_offset)[0] == 0xea3020c0

# HYP mode reaches __enter_kernel through the re-entry vector at this site.
zimage_offset = 0xff000
j0_offset = zimage_offset + 0x9f4
assert data[j0_offset:j0_offset + 4] == bytes.fromhex('00f004b8')

trampoline_offset = zimage_offset + 0x448
trampoline_runtime = 0x82000448
proof_offset = 0xc73a00
proof_vmaddr = prelink[0] + proof_offset - prelink[2]
assert proof_vmaddr == 0x80cbba00
assert not any(data[proof_offset:proof_offset + len(proof)])

# J0 executes in Thumb state. Install a wide branch to the trampoline.
branch_delta = trampoline_runtime - (0x820009f4 + 4)
assert branch_delta % 2 == 0
assert -(1 << 24) <= branch_delta < (1 << 24)
imm = branch_delta >> 1
s = (imm >> 23) & 1
i1 = (imm >> 22) & 1
i2 = (imm >> 21) & 1
imm10 = (imm >> 11) & 0x3ff
imm11 = imm & 0x7ff
j1 = ((~(i1 ^ s)) & 1)
j2 = ((~(i2 ^ s)) & 1)
first = 0xf000 | (s << 10) | imm10
second = 0x8000 | (j1 << 13) | (j2 << 11) | imm11
struct.pack_into('<HH', data, j0_offset, first, second)

data[trampoline_offset:trampoline_offset + len(trampoline)] = trampoline
data[proof_offset:proof_offset + len(proof)] = proof
destination.write_bytes(data)

changed = [i for i, (a, b) in enumerate(zip(original, data)) if a != b]
allowed = set(range(j0_offset, j0_offset + 4))
allowed.update(range(trampoline_offset, trampoline_offset + len(trampoline)))
allowed.update(range(proof_offset, proof_offset + len(proof)))
assert changed and all(i in allowed for i in changed)
assert data[entry_offset:entry_offset + 4] == original[entry_offset:entry_offset + 4]
assert data[zimage_offset:j0_offset] == original[zimage_offset:j0_offset]
assert data[j0_offset + 4:trampoline_offset] == original[j0_offset + 4:trampoline_offset]
assert data[trampoline_offset + len(trampoline):zimage_offset + 0x500] == original[trampoline_offset + len(trampoline):zimage_offset + 0x500]

print(f'candidate sha256: {expected}')
print('Mach-O entry and all code through H1: unchanged')
print('HYP re-entry vector: runtime 0x820009f4 -> kernel-entry trampoline')
print('decompressed Image first word: 0x80008000 -> ARM proof')
print(f'trampoline: {trampoline_runtime | 1:#010x} ({len(trampoline)} bytes)')
print(f'proof: {proof_vmaddr:#010x} ({len(proof)} bytes)')
print(f'raw sha256: {hashlib.sha256(data).hexdigest()}')
PY

"$xpwntool" "$output" "$packed_output" -t "$template" \
	-iv "$kernel_iv" -k "$kernel_key"
"$xpwntool" "$packed_output" "$roundtrip_output" \
	-iv "$kernel_iv" -k "$kernel_key"
cmp "$output" "$roundtrip_output"
rm -f "$roundtrip_output"

echo "verified decrypt-after-repack round trip"
sha256sum "$proof_raw" "$output" "$packed_output"

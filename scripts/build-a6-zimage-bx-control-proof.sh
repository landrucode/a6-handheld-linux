#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
candidate="$repo_root/build/arm/a6-linux-kernelcache.raw"
source_asm="$repo_root/boot/arm/zimage-predecompress-proof.S"
trampoline_elf="$repo_root/build/arm/a6-zimage-bx-control-trampoline.elf"
trampoline_raw="$repo_root/build/arm/a6-zimage-bx-control-trampoline.bin"
proof_elf="$repo_root/build/arm/a6-zimage-bx-control-proof.elf"
proof_raw="$repo_root/build/arm/a6-zimage-bx-control-proof.bin"
output="$repo_root/build/arm/a6-linux-zimage-bx-control-proof.raw"
packed_output="$repo_root/build/arm/a6-linux-zimage-bx-control-proof.img3"
roundtrip_output="$repo_root/build/arm/a6-linux-zimage-bx-control-proof.roundtrip.raw"
template="$repo_root/.deps/legacy-ios-kit/kernelcache.release.n42"
xpwntool="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/xpwntool"
kernel_iv="a037ef50ae5bf24ae2d373345b6e5be5"
kernel_key="66b8ca4f732113f54dae9de7d1713093d6c54731c06033eef94489c168a8db3a"
proof_address="0x80cbb900"

[[ -s "$candidate" && -s "$template" && -x "$xpwntool" ]]
mkdir -p "$repo_root/build/arm"

clang --target=arm-none-eabi -mcpu=swift -mthumb -ffreestanding -fno-pic \
	-nostdlib -DTRAMPOLINE_ONLY -DPROOF_ADDRESS="$proof_address" \
	-c -o "$repo_root/build/arm/a6-zimage-bx-control-trampoline.o" "$source_asm"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$trampoline_elf" "$repo_root/build/arm/a6-zimage-bx-control-trampoline.o"
llvm-objcopy -O binary "$trampoline_elf" "$trampoline_raw"

clang --target=arm-none-eabi -mcpu=swift -mthumb -ffreestanding -fno-pic \
	-nostdlib \
	-c -o "$repo_root/build/arm/a6-zimage-bx-control-proof.o" "$repo_root/boot/arm/zimage-bx-control.S"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$proof_elf" "$repo_root/build/arm/a6-zimage-bx-control-proof.o"
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
assert trampoline == bytes.fromhex('dff800f001b9cb80'), trampoline.hex()
# This boundary is word-aligned: the literal is exactly PC + 4.
assert ((0x82000a00 + 4) & ~3) == 0x82000a04

magic, cputype, cpusubtype, filetype, ncmds, _, _ = struct.unpack_from('<7I', data, 0)
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
entry = struct.unpack_from('<I', data, thread_offset + 15 * 4)[0]
entry_offset = entry - text[0]
assert entry == 0x800b3084
assert struct.unpack_from('<I', data, entry_offset)[0] == 0xea3020c0

zimage_offset = 0xff000
site = zimage_offset + 0xa00
assert data[site:site + 8] == bytes.fromhex('4ff0000039464246')
proof_offset = 0xc73900
proof_vmaddr = prelink[0] + proof_offset - prelink[2]
assert proof_vmaddr == 0x80cbb900
assert len(proof) <= 0x400
assert not any(data[proof_offset:proof_offset + len(proof)])

data[site:site + len(trampoline)] = trampoline
data[proof_offset:proof_offset + len(proof)] = proof


changed = [i for i, (a, b) in enumerate(zip(original, data)) if a != b]
allowed = set(range(site, site + len(trampoline))) | set(range(proof_offset, proof_offset + len(proof)))
assert changed and all(i in allowed for i in changed)
assert data[entry_offset:entry_offset + 4] == original[entry_offset:entry_offset + 4]
assert data[zimage_offset:site] == original[zimage_offset:site]
assert data[0xc7338c:proof_offset] == original[0xc7338c:proof_offset]

assert data[zimage_offset + 0x448:zimage_offset + 0x480] == original[zimage_offset + 0x448:zimage_offset + 0x480]
assert data[zimage_offset + 0xa08:zimage_offset + 0xa0a] == bytes.fromhex('2047')
destination.write_bytes(data)

print(f'candidate sha256: {expected}')
print('control: redirect r4 to ARM routine, then execute original bx r4')
print('stop site: runtime 0x82000a00, __enter_kernel redirects through setup shim and original bx r4')
print(f'proof: {proof_vmaddr | 1:#010x} ({len(proof)} bytes)')
print(f'raw sha256: {hashlib.sha256(data).hexdigest()}')
PY

"$xpwntool" "$output" "$packed_output" -t "$template" -iv "$kernel_iv" -k "$kernel_key"
"$xpwntool" "$packed_output" "$roundtrip_output" -iv "$kernel_iv" -k "$kernel_key"
cmp "$output" "$roundtrip_output"
rm -f "$roundtrip_output"
echo "verified decrypt-after-repack round trip"
sha256sum "$output" "$packed_output"

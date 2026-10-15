#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="$repo_root/build/arm"
elf="$build_dir/a6-framebuffer-proof.elf"
raw="$build_dir/a6-framebuffer-proof.raw"

mkdir -p "$build_dir"

clang \
	--target=arm-none-eabi \
	-mcpu=swift \
	-marm \
	-ffreestanding \
	-fno-pic \
	-nostdlib \
	-fuse-ld=lld \
	-Wl,-T,"$repo_root/boot/arm/linker.ld" \
	-Wl,--build-id=none \
	-Wl,-e,_start \
	-o "$elf" \
	"$repo_root/boot/arm/proof.S"

llvm-objcopy -O binary "$elf" "$raw"

printf 'ELF: %s\n' "$elf"
printf 'RAW: %s\n' "$raw"
file "$raw"
sha256sum "$raw"

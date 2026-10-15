#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/build/arm"
clang --target=arm-linux-gnueabi -march=armv7-a -marm -mfloat-abi=soft \
  -Os -ffreestanding -fno-builtin -fno-stack-protector -fomit-frame-pointer \
  -Wall -Wextra -Werror -nostdlib -static -fuse-ld=lld \
  -Wl,-e,_start -Wl,--build-id=none \
  "$repo_root/rootfs/a6-mmu-test-start.S" "$repo_root/rootfs/a6-mmu-test.c" \
  -o "$repo_root/build/arm/a6-mmu-test"
sha256sum "$repo_root/build/arm/a6-mmu-test"

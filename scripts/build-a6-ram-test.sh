#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/build/arm"
ram_test_mib=${A6_RAM_TEST_MIB:-256}
case "$ram_test_mib" in
  256) ram_test_output=a6-ram-test ;;
  640) ram_test_output=a6-ram-test640 ;;
  *) echo 'A6_RAM_TEST_MIB must be256 or640' >&2; exit 1 ;;
esac
clang --target=arm-linux-gnueabi -march=armv7-a -marm -mfloat-abi=soft \
  -DA6_RAM_TEST_MIB="$ram_test_mib" \
  -Os -ffreestanding -fno-builtin -fno-stack-protector -fomit-frame-pointer \
  -Wall -Wextra -Werror -nostdlib -static -fuse-ld=lld \
  -Wl,-e,_start -Wl,--build-id=none \
  "$repo_root/rootfs/a6-mmu-test-start.S" "$repo_root/rootfs/a6-ram-test.c" \
  -o "$repo_root/build/arm/$ram_test_output"
sha256sum "$repo_root/build/arm/$ram_test_output"

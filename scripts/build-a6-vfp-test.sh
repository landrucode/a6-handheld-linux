#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/build/arm"
clang --target=arm-linux-gnueabihf -march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard \
  -nostdlib -static -fuse-ld=lld -Wl,-e,_start -Wl,--build-id=none \
  "$repo_root/rootfs/a6-vfp-test.S" -o "$repo_root/build/arm/a6-vfp-test"
sha256sum "$repo_root/build/arm/a6-vfp-test"

#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
sysroot="$repo/build/aquamarine-sysroot"
mkdir -p "$repo/build/wifi-native"
clang --target=arm-linux-gnueabihf --sysroot="$sysroot" \
 --gcc-install-dir="$sysroot/usr/lib/gcc/armv7l-unknown-linux-gnueabihf/16.1.1" \
 -march=armv7-a -mfpu=neon -mfloat-abi=hard -fuse-ld=lld -O2 -fPIC -shared \
 -Wl,-z,relro,-z,now -o "$repo/build/wifi-native/touch-offset.so" \
 "$repo/rootfs/a6-touch-offset.c" -ldl

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/wifi-native
clang --target=armv7a-linux-gnueabi -marm -fuse-ld=lld \
    -fomit-frame-pointer -fno-stack-protector -ffreestanding -fno-builtin \
    -fno-unwind-tables -fno-asynchronous-unwind-tables -Oz -nostdlib -static \
    -Wl,-e,_start -Wl,--build-id=none rootfs/a6-wifi-heartbeat.c \
    -o build/wifi-native/heartbeat

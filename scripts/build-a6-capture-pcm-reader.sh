#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
# Use an out-of-tree directory so headers_install cannot dirty kernel sources.
make -s -C .deps/linux O="$PWD/build/audio-uapi-output" ARCH=arm INSTALL_HDR_PATH="$PWD/build/audio-uapi" headers_install >build/audio-uapi.private.log 2>&1
mkdir -p build/audio-reader-headers
printf '#include <stddef.h>\n' >build/audio-reader-headers/stdlib.h
printf 'typedef long time_t;\n' >build/audio-reader-headers/time.h
clang --target=arm-linux-gnueabi -march=armv7-a -marm -O2 -ffreestanding -fno-builtin -fno-stack-protector -nostdlib -static -fuse-ld=lld -Wl,-e,_start -I build/audio-reader-headers -I build/audio-uapi/include scripts/a6-capture-pcm-reader.c -o build/a6-capture-pcm-reader
python3 scripts/test-a6-capture-pcm-reader.py

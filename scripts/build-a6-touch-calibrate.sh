#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stage="$repo/build/touch-calibration"
sysroot="$repo/build/aquamarine-sysroot"
mkdir -p "$stage"
xml="$repo/.deps/wvkbd/proto/wlr-layer-shell-unstable-v1.xml"
wayland-scanner client-header "$xml" "$stage/wlr-layer-shell-unstable-v1-client-protocol.h"
wayland-scanner private-code "$xml" "$stage/layer-shell.c"
wayland-scanner private-code "$repo/.deps/wvkbd/proto/xdg-shell.xml" "$stage/xdg-shell.c"
export PKG_CONFIG_SYSROOT_DIR="$sysroot" PKG_CONFIG_LIBDIR="$sysroot/usr/lib/pkgconfig:$sysroot/usr/share/pkgconfig"
clang --target=arm-linux-gnueabihf --sysroot="$sysroot" \
 --gcc-install-dir="$sysroot/usr/lib/gcc/armv7l-unknown-linux-gnueabihf/16.1.1" \
 -march=armv7-a -mfpu=neon -mfloat-abi=hard -fuse-ld=lld -O2 -fPIE \
 -fstack-protector-strong -D_FORTIFY_SOURCE=2 -Wall -Wextra -Werror \
 -I"$stage" $(pkg-config --cflags wayland-client cairo) \
 "$repo/rootfs/a6-touch-calibrate.c" "$stage/layer-shell.c" "$stage/xdg-shell.c" \
 $(pkg-config --libs wayland-client cairo) -pie -Wl,-z,relro,-z,now \
 -o "$stage/a6-touch-calibrate"
llvm-strip --strip-debug "$stage/a6-touch-calibrate"

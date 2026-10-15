#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stage="$repo/build/app-panel"
sysroot="$repo/build/aquamarine-sysroot"
python3 "$repo/scripts/prepare-a6-labwc-runtime.py"
bash "$repo/scripts/build-a6-app-panel.sh"
wayland-scanner client-header "$repo/build/labwc/foreign-toplevel.xml" "$stage/foreign-toplevel-client.h"
wayland-scanner private-code "$repo/build/labwc/foreign-toplevel.xml" "$stage/foreign-toplevel.c"
export PKG_CONFIG_SYSROOT_DIR="$sysroot" PKG_CONFIG_LIBDIR="$sysroot/usr/lib/pkgconfig:$sysroot/usr/share/pkgconfig"
flags=(-ffile-prefix-map="$repo"=. -fdebug-prefix-map="$repo"=. --target=arm-linux-gnueabihf --sysroot="$sysroot" --gcc-install-dir="$sysroot/usr/lib/gcc/armv7l-unknown-linux-gnueabihf/16.1.1" -march=armv7-a -mfpu=neon -mfloat-abi=hard -O2 -fPIE -fstack-protector-strong -D_FORTIFY_SOURCE=2)
clang "${flags[@]}" $(pkg-config --cflags wayland-client) -c "$stage/foreign-toplevel.c" -o "$stage/foreign-toplevel.o"
clang++ "${flags[@]}" -std=c++20 -fuse-ld=lld -I"$stage" $(pkg-config --cflags wayland-client cairo) \
 "$repo/rootfs/a6-labwc-panel.cpp" "$stage/foreign-toplevel.o" "$stage/layer-shell.o" "$stage/xdg-shell.o" \
 $(pkg-config --libs wayland-client cairo) -pie -Wl,-z,relro,-z,now -o "$stage/a6-labwc-panel"
llvm-strip --strip-debug "$stage/a6-labwc-panel"

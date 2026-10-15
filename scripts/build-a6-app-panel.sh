#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stage="$repo/build/app-panel"
sysroot="$repo/build/aquamarine-sysroot"
mkdir -p "$stage"
bash "$repo/scripts/build-a6-touch-calibrate.sh"
sed 's/\bnamespace\b/layer_namespace/g' "$repo/build/touch-calibration/wlr-layer-shell-unstable-v1-client-protocol.h" >"$stage/wlr-layer-shell-unstable-v1-client-protocol.h"
export PKG_CONFIG_SYSROOT_DIR="$sysroot" PKG_CONFIG_LIBDIR="$sysroot/usr/lib/pkgconfig:$sysroot/usr/share/pkgconfig"
flags=(-ffile-prefix-map="$repo"=. -fdebug-prefix-map="$repo"=. --target=arm-linux-gnueabihf --sysroot="$sysroot" --gcc-install-dir="$sysroot/usr/lib/gcc/armv7l-unknown-linux-gnueabihf/16.1.1" -march=armv7-a -mfpu=neon -mfloat-abi=hard -O2 -fPIE -fstack-protector-strong -D_FORTIFY_SOURCE=2)
for file in layer-shell xdg-shell; do
 clang "${flags[@]}" $(pkg-config --cflags wayland-client) -c "$repo/build/touch-calibration/$file.c" -o "$stage/$file.o"
done
clang++ "${flags[@]}" -std=c++20 -fuse-ld=lld -I"$stage" -I"$repo/.deps/jsoncpp/include" \
 $(pkg-config --cflags wayland-client cairo) "$repo/rootfs/a6-app-panel.cpp" \
 "$repo"/build/oomd/jsoncpp_src_lib_json_*.o "$stage/layer-shell.o" "$stage/xdg-shell.o" \
 $(pkg-config --libs wayland-client cairo) -pie -Wl,-z,relro,-z,now -o "$stage/a6-app-panel"
llvm-strip --strip-debug "$stage/a6-app-panel"

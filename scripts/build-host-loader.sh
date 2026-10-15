#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
irecovery_dir="$repo_root/.deps/libirecovery"
bootkit_dir="$repo_root/.deps/checkm8_bootkit"
output_dir="$repo_root/build/host"
output_path="$output_dir/checkm8-bootkit-linux"

if [[ ! -d "$irecovery_dir" || ! -d "$bootkit_dir" ]]; then
  printf 'missing .deps/libirecovery or .deps/checkm8_bootkit; prepare them before building\n' >&2
  exit 1
fi

make -C "$irecovery_dir" -j"$(nproc)"
mkdir -p "$output_dir"

gcc \
  -D_GNU_SOURCE \
  -std=gnu11 \
  -O2 \
  -Wall \
  -Wextra \
  -I"$repo_root/boot/host/include" \
  -I"$bootkit_dir/src" \
  -I"$bootkit_dir/src/libbootkit" \
  -I"$irecovery_dir/include" \
  "$repo_root/boot/host/checkm8_bootkit_linux.c" \
  "$bootkit_dir/src/libbootkit/log.c" \
  "$bootkit_dir/src/libbootkit/boot.c" \
  "$bootkit_dir/src/libbootkit/dfu.c" \
  "$bootkit_dir/src/libbootkit/protocol.c" \
  -L"$irecovery_dir/src/.libs" \
  -Wl,-rpath,"$irecovery_dir/src/.libs" \
  -lirecovery-1.0 \
  -o "$output_path"

printf 'built %s\n' "$output_path"

#!/usr/bin/env bash
# Compile-only dependency proof. No boot profile, IMG3 or phone operation.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
linux_root="$repo_root/.deps/linux"
source_config="$repo_root/build/linux-a6-low-battery-boot-defaults-smp-first-scheduling/.config"
output_root="$repo_root/build/linux-a6-ram-root-compile"
mkdir -p "$output_root" "$repo_root/build/session-logs"
cp "$source_config" "$output_root/.config"
KCONFIG_CONFIG="$output_root/.config" \
    "$linux_root/scripts/kconfig/merge_config.sh" -m -O "$output_root" \
    "$output_root/.config" "$repo_root/kernel/a6-ram-root.config"
make -C "$linux_root" O="$output_root" ARCH=arm LLVM=1 LLVM_IAS=1 olddefconfig
python3 - "$source_config" "$output_root/.config" <<'PY'
import hashlib
from pathlib import Path
import sys
source, target = map(Path, sys.argv[1:])
config = target.read_text()
for symbol in ('BLOCK', 'BLK_DEV_LOOP', 'SQUASHFS', 'SQUASHFS_ZSTD',
               'OVERLAY_FS', 'TMPFS_XATTR', 'SWAP', 'ZSMALLOC', 'ZRAM',
               'ZRAM_BACKEND_LZ4', 'ZRAM_DEF_COMP_LZ4', 'SMP'):
    if f'CONFIG_{symbol}=y\n' not in config:
        raise SystemExit('required feature unresolved: ' + symbol)
for symbol in ('HOTPLUG_CPU', 'CPU_IDLE', 'ZRAM_WRITEBACK', 'KEXEC'):
    if f'CONFIG_{symbol}=y\n' in config:
        raise SystemExit('unexpected feature enabled: ' + symbol)
print('source_config_sha256=' + hashlib.sha256(source.read_bytes()).hexdigest())
print('candidate_config_sha256=' + hashlib.sha256(target.read_bytes()).hexdigest())
print('RAM-root dependencies resolved; SMP retained, no hotplug/idle/kexec/writeback')
PY
make -C "$linux_root" O="$output_root" ARCH=arm LLVM=1 LLVM_IAS=1 -j4 \
    fs/squashfs/ fs/overlayfs/ drivers/block/zram/ \
    drivers/block/loop.o mm/zsmalloc.o mm/swapfile.o

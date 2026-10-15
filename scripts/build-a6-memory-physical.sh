#!/usr/bin/env bash
# Repack the checked memory-capture kernel with the corrected handoff only.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_ZIMAGE="$repo_root/build/linux-a6-arch-memory-capture/arch/arm/boot/zImage"
export A6_DTB="$repo_root/build/arm/a6-n42ap-arch-memory-capture.dtb"
python3 - "$A6_ZIMAGE" "$A6_DTB" <<'PY'
import hashlib,sys
from pathlib import Path
for p,h in zip(sys.argv[1:],[
 '74a5e45fcee2c46cacae6ad74ad24d13c502f373072b3f84af37e804f6290d0c',
 '2dc6e11eb70b10df655ca49124b27921f338b051769d6b15a6341ae97e2bece5']):
 assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h, p
print('PASS unchanged checked kernel and DT')
PY
export A6_MEMORY_CAPTURE=1 A6_USB_NETWORK=1 A6_USB_SHELL=1
export A6_PAYLOAD="$repo_root/build/arm/a6-n42ap-arch-memory-physical-zImage-with-dtb"
export A6_KERNELCACHE_RAW="$repo_root/build/arm/a6-linux-arch-memory-physical.raw"
export A6_KERNELCACHE_IMG3="$repo_root/build/arm/a6-linux-arch-memory-physical.img3"
export A6_KERNELCACHE_ROUNDTRIP="$repo_root/build/arm/a6-linux-arch-memory-physical.roundtrip.raw"
bash scripts/build-a6-kernelcache.sh

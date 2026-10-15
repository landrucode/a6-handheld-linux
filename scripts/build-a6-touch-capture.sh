#!/usr/bin/env bash
# Read-only calibration capture; same proven Linux kernel and768MiB DT.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
python3 - <<'PY'
from pathlib import Path
import hashlib
pins={
 'build/linux-a6-arch-direct-drm/arch/arm/boot/zImage':'d02081e7cf1a3a790d2bd5fd37aff52f87b1fd14f8c2ca8b5137911156e09ae4',
 'build/arm/a6-n42ap-arch-direct-drm-ram768.dtb':'c0e4bf6476ba711798a0586bce7277febf7591c0bbeb40088b12282090a72a88',
 'build/arm/a6-linux-arch-direct-drm-ram768.img3':'c5955b367f20c5c7d5da2606906cf7b2ec8504ee9451b376cf58fd782f7f4e7f'}
for p,h in pins.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
print('PASS unchanged proven kernel,768MiB DT and fallback image')
PY
export A6_ZIMAGE="$repo_root/build/linux-a6-arch-direct-drm/arch/arm/boot/zImage"
export A6_DTB="$repo_root/build/arm/a6-n42ap-arch-direct-drm-ram768.dtb"
export A6_MEMORY_CAPTURE=1 A6_CAPTURE_TOUCH=1 A6_USB_NETWORK=1 A6_USB_SHELL=1
export A6_PAYLOAD="$repo_root/build/arm/a6-n42ap-touch-capture-zImage-with-dtb"
export A6_KERNELCACHE_RAW="$repo_root/build/arm/a6-linux-touch-capture.raw"
export A6_KERNELCACHE_IMG3="$repo_root/build/arm/a6-linux-touch-capture.img3"
export A6_KERNELCACHE_ROUNDTRIP="$repo_root/build/arm/a6-linux-touch-capture.roundtrip.raw"
bash scripts/build-a6-kernelcache.sh
cmp build/arm/a6-n42ap-touch-capture-zImage-with-dtb build/arm/a6-n42ap-arch-direct-drm-ram768-zImage-with-dtb
python3 - <<'CHECK'
from pathlib import Path
old=Path('build/arm/a6-linux-arch-direct-drm-ram768.raw').read_bytes()
new=Path('build/arm/a6-linux-touch-capture.raw').read_bytes()
assert len(old)==len(new)
assert old[:0xc7338c]==new[:0xc7338c]
assert old[0xc7438c:]==new[0xc7438c:]
print('PASS all image changes confined to existing4KiB handoff cave')
CHECK
sha256sum "$A6_KERNELCACHE_IMG3"

#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="$repo_root/build/arm"
firmware_dir="$repo_root/.deps/legacy-ios-kit/firmware"
img3maker="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/img3maker"

proof_raw="$build_dir/a6-framebuffer-proof.raw"
liveness_raw="$build_dir/a6-diag-liveness.raw"
ibec_raw="$firmware_dir/iBEC.n42.RELEASE.patched"
ibec_diag_raw="$build_dir/iBEC.n42.RELEASE.diag.raw"
ibec_diag_img3="$build_dir/iBEC.n42.RELEASE.diag.dfu"
proof_img3="$build_dir/a6-framebuffer-proof.img3"

[[ -s "$proof_raw" ]] || {
	echo "missing $proof_raw; run scripts/build-proof-loader.sh first" >&2
	exit 1
}
clang \
	--target=arm-none-eabi \
	-mcpu=swift \
	-marm \
	-ffreestanding \
	-fno-pic \
	-nostdlib \
	-fuse-ld=lld \
	-Wl,-T,"$repo_root/boot/arm/linker.ld" \
	-Wl,--build-id=none \
	-Wl,-e,_start \
	-o "$build_dir/a6-diag-liveness.elf" \
	"$repo_root/boot/arm/liveness.S"
llvm-objcopy -O binary "$build_dir/a6-diag-liveness.elf" "$liveness_raw"
[[ -s "$ibec_raw" ]] || {
	echo "missing $ibec_raw" >&2
	exit 1
}
[[ -x "$img3maker" ]] || {
	echo "missing executable $img3maker" >&2
	exit 1
}

mkdir -p "$build_dir"

# iBEC iBoot-2261.30.37's go handler loads BOOT_UNKNOWN (0) into R0 at this
# exact instruction. The A6 diagnostic handoff needs BOOT_DIAGS (5). Keep
# this assertion tied to the source bytes so a firmware revision cannot be
# patched accidentally.
python3 - "$ibec_raw" "$ibec_diag_raw" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
data = bytearray(source.read_bytes())
offset = 0x117c
expected = bytes.fromhex("00 20")
replacement = bytes.fromhex("05 20")

if data[offset:offset + 2] != expected:
    got = data[offset:offset + 2].hex(" ")
    raise SystemExit(f"unexpected iBEC bytes at 0x{offset:x}: {got}")

data[offset:offset + 2] = replacement
destination.write_bytes(data)
print(f"patched {source.name}: 0x{offset:x} {expected.hex(' ')} -> {replacement.hex(' ')}")
PY

"$img3maker" -f "$ibec_diag_raw" -o "$ibec_diag_img3" -t ibec
"$img3maker" -f "$proof_raw" -o "$proof_img3" -t diag
"$img3maker" -f "$liveness_raw" -o "$build_dir/a6-diag-liveness.img3" -t diag

sha256sum "$ibec_diag_img3" "$proof_raw" "$proof_img3" "$liveness_raw" "$build_dir/a6-diag-liveness.img3"

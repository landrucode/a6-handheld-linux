#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
linux_root="$repo_root/.deps/linux"
output_root="$repo_root/build/linux-a6-baseline"
fragment="$repo_root/kernel/a6-minimal.config"
dts="$repo_root/device-tree/a6-n42ap.dts"
dtb="$repo_root/build/arm/a6-n42ap-baseline.dtb"
combined="$repo_root/build/arm/a6-n42ap-baseline-zImage-with-dtb"
init_binary="$repo_root/build/arm/a6-init-baseline"
initramfs_list="$repo_root/build/arm/a6-initramfs-baseline.list"

for command_name in clang make python3 bc; do
	command -v "$command_name" >/dev/null || {
		echo "missing required command: $command_name" >&2
		exit 1
	}
done

mkdir -p "$output_root" "$repo_root/build/arm"
clang --target=arm-none-eabi -mcpu=swift -marm -nostdlib -static \
	-fuse-ld=lld -Wl,-e,_start -Wl,--build-id=none \
	-o "$init_binary" "$repo_root/rootfs/a6-init.S"
printf '%s\n' \
	'dir /dev 0755 0 0' \
	'nod /dev/console 0600 0 0 c 5 1' \
	"file /init $init_binary 0755 0 0" >"$initramfs_list"

stash="$(mktemp -d "${TMPDIR:-/tmp}/a6-baseline.XXXXXX")"
irq_make="$linux_root/drivers/irqchip/Makefile"
timer_make="$linux_root/drivers/clocksource/Makefile"
tlb_header="$linux_root/arch/arm/include/asm/tlbflush.h"
tlb_v7="$linux_root/arch/arm/mm/tlb-v7.S"
mmu="$linux_root/arch/arm/mm/mmu.c"
compressed_head="$linux_root/arch/arm/boot/compressed/head.S"
irq_dest="$linux_root/drivers/irqchip/irq-apple-a6-aic.c"
timer_dest="$linux_root/drivers/clocksource/timer-apple-a6.c"

for source in "$irq_make" "$timer_make" "$tlb_header" "$tlb_v7" "$mmu" "$compressed_head"; do
	cp -- "$source" "$stash/$(basename -- "$source").$(stat -c %i "$source")"
done

restore_tree() {
	status=$?
	trap - EXIT HUP INT TERM
	for source in "$irq_make" "$timer_make" "$tlb_header" "$tlb_v7" "$mmu" "$compressed_head"; do
		cp -- "$stash/$(basename -- "$source").$(stat -c %i "$source")" "$source"
	done
	rm -f -- "$irq_dest" "$timer_dest"
	rm -rf -- "$stash"
	exit "$status"
}
trap restore_tree EXIT HUP INT TERM

cp -- "$repo_root/kernel/platform/irq-apple-a6-aic.c" "$irq_dest"
cp -- "$repo_root/kernel/platform/timer-apple-a6.c" "$timer_dest"
printf '%s\n' 'obj-y += irq-apple-a6-aic.o' >>"$irq_make"
printf '%s\n' 'obj-y += timer-apple-a6.o' >>"$timer_make"

# Retain cached execution for the decompressor, but override the five identity
# sections containing the inflated Image as non-cacheable. The output then
# needs no Swift maintenance operation at handoff. Unlike the diagnostic
# profile this adds no framebuffer writes or execution markers.
python3 - "$compressed_head" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()

pattern = r"(__armv7_mmu_cache_flush:\n).*?(\n__armv5tej_mmu_cache_flush:)"
replacement = r"""\1
		dsb	sy
		isb	sy
		mov	pc, lr
\2"""
text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count != 1:
    raise SystemExit("could not isolate ARMv7 decompressor cache flush")

anchor = """\t\tteq\tr0, r2
\t\tbne\t1b
/*
 * If ever we are running from Flash, then we surely want the cache
"""
replacement = """\t\tteq\tr0, r2
\t\tbne\t1b

\t\t/* A6: inflated Image is 0x80008000..0x804735a0. Keep all
\t\t * five containing identity sections non-cacheable. */
\t\tmov\tr2, #0x800
\t\tadd\tr0, r3, r2, lsl #2
\t\tmov\tr1, r2, lsl #20
\t\torr\tr1, r1, #3 << 10
\t\torr\tr1, r1, #0x02
\t\tmov\tr2, #5
9:\t\tstr\tr1, [r0], #4
\t\tadd\tr1, r1, #1048576
\t\tsubs\tr2, r2, #1
\t\tbne\t9b
/*
 * If ever we are running from Flash, then we surely want the cache
"""
if text.count(anchor) != 1:
    raise SystemExit("could not locate decompressor section-map loop")
text = text.replace(anchor, replacement, 1)

pattern = r"(__armv7_mmu_cache_off:\n).*?(\n\s*\.align\s+5\ncache_clean_flush:)"
replacement = r"""\1
		mrc	p15, 0, r0, c1, c0, 0
		bic	r0, r0, #5
		mcr	p15, 0, r0, c1, c0, 0
		dsb	sy
		isb	sy
		mov	pc, lr
\2"""
text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count != 1:
    raise SystemExit("could not isolate ARMv7 decompressor cache-off path")

old = """cache_off:\tmov\tr3, #12\t\t\t@ cache_off function
\t\tb\tcall_cache_fn
"""
new = """cache_off:\tb\t__armv7_mmu_cache_off\t@ A6 Swift
"""
if text.count(old) != 1:
    raise SystemExit("could not locate decompressor cache-off dispatcher")
text = text.replace(old, new, 1)

old = """cache_clean_flush:
\t\tmov\tr3, #16
\t\tmov\tr11, r1
\t\tb	call_cache_fn
"""
new = """cache_clean_flush:
\t\tmov\tr11, r1
\t\tb	__armv7_mmu_cache_flush\t@ A6 Swift
"""
if text.count(old) != 1:
    raise SystemExit("could not locate decompressor cache-flush dispatcher")
path.write_text(text.replace(old, new, 1))
PY

# Temporary and unsafe: retained only so the clean baseline reaches the same
# platform-init point as the historical diagnostic image.
python3 - "$tlb_header" "$tlb_v7" "$mmu" <<'PY'
from pathlib import Path
import re
import sys

header, assembly, mmu = map(Path, sys.argv[1:])
text = header.read_text()
text = re.sub(r'#define v7wbi_tlb_flags_smp.*?TLB_V7_UIS_BP\)',
              '#define v7wbi_tlb_flags_smp\t(TLB_WB | TLB_BARRIER)', text,
              count=1, flags=re.S)
text = re.sub(r'#define v7wbi_tlb_flags_up.*?TLB_V6_BP\)',
              '#define v7wbi_tlb_flags_up\t(TLB_WB | TLB_BARRIER)', text,
              count=1, flags=re.S)
header.write_text(text)

text = assembly.read_text()
for name in ('v7wbi_flush_user_tlb_range', 'v7wbi_flush_kern_tlb_range'):
    pattern = rf'(SYM_TYPED_FUNC_START\({name}\)\n).*?(SYM_FUNC_END\({name}\))'
    text, count = re.subn(pattern, rf'\1\tdsb\tish\n\tisb\n\tret\tlr\n\2',
                          text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'could not isolate {name}')
assembly.write_text(text)

text = mmu.read_text()
old = '\tlocal_flush_tlb_all();\n\tflush_cache_all();\n'
if text.count(old) != 1:
    raise SystemExit('could not isolate boot-time TLB flush')
mmu.write_text(text.replace(old, '\tdsb(ish); /* A6 bring-up workaround */\n\tflush_cache_all();\n'))
PY

make_args=(-C "$linux_root" O="$output_root" ARCH=arm LLVM=1 LLVM_IAS=1)
make "${make_args[@]}" tinyconfig
KCONFIG_CONFIG="$output_root/.config" \
	"$linux_root/scripts/kconfig/merge_config.sh" -m -O "$output_root" \
	"$output_root/.config" "$fragment"
make "${make_args[@]}" olddefconfig
"$linux_root/scripts/config" --file "$output_root/.config" \
	--enable BLK_DEV_INITRD --set-str INITRAMFS_SOURCE "$initramfs_list"
make "${make_args[@]}" olddefconfig
make "${make_args[@]}" -j"$(nproc)" zImage scripts_dtc

"$output_root/scripts/dtc/dtc" -I dts -O dtb -o "$dtb" "$dts"
cp -- "$output_root/arch/arm/boot/zImage" "$combined"
dd if="$dtb" of="$combined" bs=1 oflag=append conv=notrunc status=none

file "$output_root/arch/arm/boot/zImage" "$dtb" "$combined"
sha256sum "$output_root/arch/arm/boot/zImage" "$dtb" "$combined"

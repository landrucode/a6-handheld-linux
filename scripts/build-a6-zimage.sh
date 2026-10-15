#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
linux_root="$repo_root/.deps/linux"
legacy_control="${A6_LEGACY_CONTROL:-0}"
if [[ "$legacy_control" == 1 ]]; then
	output_root="$repo_root/build/linux-a6-legacy-control"
	dts="$repo_root/device-tree/a6-n42ap-legacy-control.dts"
	dtb="$repo_root/build/arm/a6-n42ap-legacy-control.dtb"
	combined="$repo_root/build/arm/a6-n42ap-legacy-control-zImage-with-dtb"
else
	output_root="$repo_root/build/linux-a6"
	dts="$repo_root/device-tree/a6-n42ap.dts"
	dtb="$repo_root/build/arm/a6-n42ap.dtb"
	combined="$repo_root/build/arm/a6-n42ap-zImage-with-dtb"
fi
output_root="${A6_OUTPUT_ROOT:-$output_root}"
dtb="${A6_DTB_OUTPUT:-$dtb}"
combined="${A6_COMBINED_OUTPUT:-$combined}"
fragment="$repo_root/kernel/a6-minimal.config"
usb_console="${A6_USB_CONSOLE:-0}"
usb_boot_status="${A6_USB_BOOT_STATUS:-0}"
if [[ "${A6_SMP_LOCAL_TLBI:-0}" == 1 ]]; then
    [[ "${A6_SMP_COMPILE_ONLY:-0}" == 1 && "${A6_LOCAL_FULL_TLBI:-0}" == 1 ]]
fi
if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
    [[ "${A6_SMP_COMPILE_ONLY:-0}" == 1 && "${A6_SMP_LOCAL_TLBI:-0}" == 1 &&
       "${A6_USB_NETWORK:-0}" == 1 ]]
fi
if [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
    [[ "${A6_SMP_COMPILE_ONLY:-0}" == 1 && "${A6_SMP_LOCAL_TLBI:-0}" == 1 &&
       "${A6_SMP_CPU0_ONLY:-0}" != 1 && "${A6_CPU1_PREFLIGHT:-0}" != 1 ]]
fi
[[ "$usb_boot_status" == 0 || "$usb_console" == 1 ]]
if [[ "${A6_USB_BUS_POWERED:-0}" == 1 ]]; then
    [[ "$usb_console" == 1 && "${A6_USB_NETWORK:-0}" == 1 ]]
fi
if [[ "$usb_console" == 1 ]]; then
	[[ "$legacy_control" == 0 && "$output_root" != "$repo_root/build/linux-a6" ]]
	dts="$repo_root/device-tree/a6-n42ap-usb-console.dts"
    if [[ "${A6_TIMER_A2:-0}" == 1 ]]; then
        dts="$repo_root/device-tree/a6-n42ap-usb-timer-a2.dts"
    fi
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
        [[ "${A6_TIMER_A2:-0}" == 1 ]]
        dts="$repo_root/device-tree/a6-n42ap-smp-cpu0-only.dts"
    fi
    if [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        [[ "${A6_TIMER_A2:-0}" == 1 ]]
        dts="$repo_root/device-tree/a6-n42ap-smp-bridge-quarantine.dts"
    fi
    if [[ "${A6_DWC2_FULL_SPEED_ONLY:-0}" == 1 ]]; then
        [[ "${A6_TIMER_A2:-0}" == 1 ]]
        dts="$repo_root/device-tree/a6-n42ap-usb-full-speed.dts"
    fi
fi
if [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 && "${A6_CPU1_IPI_CHECKPOINTS:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 && "${A6_SMP_COMPILE_ONLY:-0}" != 1 ]]
fi
if [[ "${A6_CPU1_CACHE_TRE_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_CACHE_REPEAT_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_CACHE_TRE_PROBE:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_CACHE_SHAREABLE_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_CACHE_REPEAT_PROBE:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_IPI_CHECKPOINTS:-0}" == 1 ]]; then
    [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_ENTRY_PROBE:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_ENTRY_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_ALIAS_WRITE:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_ALIAS_WRITE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_ALIAS_PREFLIGHT:-0}" == 1 ]]
fi
if [[ "${A6_CPU1_ALIAS_PREFLIGHT:-0}" == 1 ]]; then
    [[ "${A6_CPU1_PREFLIGHT:-0}" == 1 && "${A6_TIMER_A2:-0}" == 1 ]]
    [[ "${A6_SMP_COMPILE_ONLY:-0}" != 1 && "${A6_DWC2_FULL_SPEED_ONLY:-0}" != 1 ]]
    dts="$repo_root/device-tree/a6-n42ap-cpu1-alias-preflight.dts"
    if [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]; then
        dts="$repo_root/device-tree/a6-n42ap-cpu1-tlbi-probe.dts"
    fi
fi
zimage="$output_root/arch/arm/boot/zImage"
init_source="$repo_root/rootfs/a6-init.S"
init_binary="$repo_root/build/arm/a6-init"
initramfs_list="$repo_root/build/arm/a6-initramfs.list"
if [[ "$usb_console" == 1 ]]; then
	init_source="$repo_root/rootfs/a6-usb-init.S"
	init_binary="$repo_root/build/arm/a6-usb-init"
initramfs_list="$repo_root/build/arm/a6-usb-initramfs.list"
fi
if [[ "${A6_USB_SHELL:-0}" == 1 ]]; then
    [[ "$usb_console" == 1 ]]
    init_source="$repo_root/rootfs/a6-usb-shell-init.S"
    init_binary="$repo_root/build/arm/a6-usb-shell-init"
    initramfs_list="$repo_root/build/arm/a6-usb-shell-initramfs.list"
fi

for command_name in clang make python3; do
	command -v "$command_name" >/dev/null || {
		echo "missing required command: $command_name" >&2
		exit 1
	}
done

command -v bc >/dev/null || {
	echo "missing required command: bc (the Linux kernel uses it for timeconst.h)" >&2
	exit 1
}

[[ -d "$linux_root" ]] || {
	echo "missing Linux source tree: $linux_root" >&2
	exit 1
}
[[ -r "$fragment" ]] || {
	echo "missing kernel config fragment: $fragment" >&2
	exit 1
}
[[ -r "$dts" ]] || {
	echo "missing device tree source: $dts" >&2
	exit 1
}

mkdir -p "$output_root" "$(dirname -- "$dtb")"

clang --target=arm-none-eabi -mcpu=swift -marm -nostdlib -static \
	-DA6_USB_NETWORK="${A6_USB_NETWORK:-0}" \
	-fuse-ld=lld -Wl,-e,_start -Wl,--build-id=none \
	-o "$init_binary" "$init_source"
cat >"$initramfs_list" <<EOF
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
file /init $init_binary 0755 0 0
EOF
if [[ "${A6_USB_SHELL:-0}" == 1 ]]; then
    python3 "$repo_root/scripts/make-a6-shell-rootfs.py" "$repo_root" "$init_binary" "$initramfs_list"
fi

if [[ "${A6_WIFI_USB_IDENTITY:-0}" == 1 ]]; then
    [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]] || {
        echo 'A6_WIFI_USB_IDENTITY requires A6_WIFI_EHCI_ENUM=1' >&2
        exit 1
    }
fi

if [[ "${A6_WIFI_USB_OTP:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_IDENTITY:-0}" == 1 ]] || {
        echo 'A6_WIFI_USB_OTP requires A6_WIFI_USB_IDENTITY=1' >&2
        exit 1
    }
fi

if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_EXECUTE:-0}" == 1 && "${A6_WIFI_USB_RUNTIME:-0}" == 1 ]] || { echo "Native Wi-Fi needs proven firmware startup/runtime" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_SCAN:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_RUNTIME:-0}" == 1 && "${A6_WIFI_USB_RX:-0}" == 1 && "${A6_WIFI_USB_PREFLIGHT:-0}" != 1 && "${A6_WIFI_USB_COUNTRY:-0}" != 1 && "${A6_WIFI_USB_LOOPBACK:-0}" != 1 ]] || { echo "Scan requires runtime/RX and excludes preflight/country/loopback" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_COUNTRY:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_PREFLIGHT:-0}" == 1 ]] || { echo "Country trial requires preflight" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_PREFLIGHT:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_RUNTIME:-0}" == 1 && "${A6_WIFI_USB_RX:-0}" != 1 && "${A6_WIFI_USB_LOOPBACK:-0}" != 1 ]] || { echo "Read-only preflight requires runtime, excludes RX/loopback" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_LOOPBACK_BAD_CHECKSUM:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_LOOPBACK:-0}" == 1 ]] || { echo "Bad-checksum control requires loopback" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_LOOPBACK:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_RX:-0}" == 1 ]] || { echo "A6_WIFI_USB_LOOPBACK requires passive RX" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_RX:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_RUNTIME:-0}" == 1 ]] || { echo "A6_WIFI_USB_RX requires runtime control" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_RUNTIME:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_EXECUTE:-0}" == 1 ]] || { echo "A6_WIFI_USB_RUNTIME requires execution" >&2; exit 1; }
fi
if [[ "${A6_WIFI_USB_EXECUTE:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_DOWNLOAD:-0}" == 1 ]] || {
        echo 'A6_WIFI_USB_EXECUTE requires A6_WIFI_USB_DOWNLOAD=1' >&2
        exit 1
    }
    python3 "$repo_root/scripts/verify-a6-wifi-host-ready.py" > "$repo_root/build/session-logs/wifi-host-ready-build-verification.json"
fi

if [[ "${A6_WIFI_USB_DOWNLOAD:-0}" == 1 ]]; then
    [[ "${A6_WIFI_USB_OTP:-0}" == 1 ]] || {
        echo 'A6_WIFI_USB_DOWNLOAD requires A6_WIFI_USB_OTP=1' >&2
        exit 1
    }
    mkdir -p "$repo_root/build/wifi-firmware"
    python3 "$repo_root/scripts/prepare-a6-wifi-trx.py" > "$repo_root/build/wifi-firmware/a6-download-package.json"
    read -r a6_wifi_package a6_wifi_bytes a6_wifi_crc < <(python3 - "$repo_root" <<'PYFW'
from pathlib import Path
import hashlib, json, struct, sys
root=Path(sys.argv[1]);r=json.loads((root/'build/wifi-firmware/a6-download-package.json').read_text())
p=root/r['output'];b=p.read_bytes()
assert hashlib.sha256(b).hexdigest()==r['sha256'] and len(b)==r['bytes']
print(p, len(b), hex(struct.unpack_from('<I',b,8)[0]))
PYFW
    )
    [[ -f "$a6_wifi_package" && "$a6_wifi_bytes" =~ ^[0-9]+$ && "$a6_wifi_crc" =~ ^0x[0-9a-f]+$ ]]
fi

config_stash="$(mktemp -d "${TMPDIR:-/tmp}/a6-linux-kconfig.XXXXXX")"
if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
    [[ "${A6_WIFI_CLOCK_SNAPSHOT:-0}" == 1 && "${A6_D1972_POLICY:-0}" == 1 ]]
    [[ ! -e "$linux_root/drivers/usb/host/a6-wifi-usb-download.inc" ]]
    for name in ehci.h ehci-hub.c ehci-hcd.c Makefile; do
        cp "$linux_root/drivers/usb/host/$name" "$config_stash/ehci-$name"
    done
fi
stashed_config=0
stashed_config_dir=0
compressed_head="$linux_root/arch/arm/boot/compressed/head.S"
kernel_head="$linux_root/arch/arm/kernel/head.S"
kernel_head_common="$linux_root/arch/arm/kernel/head-common.S"
kernel_main="$linux_root/init/main.c"
kernel_setup="$linux_root/arch/arm/kernel/setup.c"
kernel_mmu="$linux_root/arch/arm/mm/mmu.c"
kernel_tlb_header="$linux_root/arch/arm/include/asm/tlbflush.h"
kernel_tlb_v7="$linux_root/arch/arm/mm/tlb-v7.S"
kernel_smp_plat="$linux_root/arch/arm/include/asm/smp_plat.h"
kernel_smp_source="$linux_root/arch/arm/kernel/smp.c"
kernel_cpuhotplug_header="$linux_root/include/linux/cpuhotplug.h"
kernel_read_write="$linux_root/fs/read_write.c"
kernel_entry_common="$linux_root/arch/arm/kernel/entry-common.S"
kernel_context="$linux_root/arch/arm/mm/context.c"
kernel_traps="$linux_root/arch/arm/kernel/traps.c"
kernel_fault="$linux_root/arch/arm/mm/fault.c"
kernel_exec="$linux_root/fs/exec.c"
kernel_elf="$linux_root/fs/binfmt_elf.c"
kernel_uart="$linux_root/drivers/tty/serial/samsung_tty.c"
irqchip_makefile="$linux_root/drivers/irqchip/Makefile"
irqchip_kconfig="$linux_root/drivers/irqchip/Kconfig"
clocksource_makefile="$linux_root/drivers/clocksource/Makefile"
audio_include_names=(a6-audio-tone.inc a6-audio-codec-play.inc a6-audio-codec.inc a6-audio-alsa.inc)
for audio_include_name in "${audio_include_names[@]}"; do
    audio_include_path="$linux_root/drivers/video/fbdev/$audio_include_name"
    if [[ -e "$audio_include_path" ]]; then
        [[ -f "$audio_include_path" && ! -L "$audio_include_path" ]]
        cp -p "$audio_include_path" "$config_stash/$audio_include_name"
    fi
done
a6_irqchip="$linux_root/drivers/irqchip/irq-apple-a6-aic.c"
a6_timer="$linux_root/drivers/clocksource/timer-apple-a6.c"
cp "$compressed_head" "$config_stash/head.S"
cp "$kernel_head" "$config_stash/kernel-head.S"
cp "$kernel_head_common" "$config_stash/kernel-head-common.S"
cp "$kernel_main" "$config_stash/kernel-main.c"
cp "$kernel_setup" "$config_stash/kernel-setup.c"
cp "$kernel_mmu" "$config_stash/kernel-mmu.c"
cp "$kernel_tlb_header" "$config_stash/kernel-tlbflush.h"
cp "$kernel_tlb_v7" "$config_stash/kernel-tlb-v7.S"
cp "$kernel_smp_plat" "$config_stash/kernel-smp-plat.h"
cp "$kernel_smp_source" "$config_stash/kernel-smp.c"
cp "$kernel_cpuhotplug_header" "$config_stash/kernel-cpuhotplug.h"
cp "$kernel_read_write" "$config_stash/kernel-read-write.c"
cp "$kernel_entry_common" "$config_stash/kernel-entry-common.S"
cp "$kernel_context" "$config_stash/kernel-context.c"
cp "$kernel_traps" "$config_stash/kernel-traps.c"
cp "$kernel_fault" "$config_stash/kernel-fault.c"
cp "$kernel_exec" "$config_stash/kernel-exec.c"
cp "$kernel_elf" "$config_stash/kernel-binfmt-elf.c"
cp "$kernel_uart" "$config_stash/kernel-samsung-tty.c"
cp "$irqchip_makefile" "$config_stash/irqchip-Makefile"
cp "$irqchip_kconfig" "$config_stash/irqchip-Kconfig"
cp "$clocksource_makefile" "$config_stash/clocksource-Makefile"
if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then
    cp "$linux_root/drivers/gpu/drm/sysfb/simpledrm.c" "$config_stash/simpledrm.c"
fi
usb_sources_installed=0
usb_power_descriptor_patched=0
fb_sources_installed=0
if [[ "${A6_FRAMEBUFFER:-0}" == 1 ]]; then
    [[ ! -e "$linux_root/drivers/video/fbdev/fb-apple-a6.c" ]]
    cp "$linux_root/drivers/video/fbdev/Makefile" "$config_stash/fbdev-Makefile"
    cp "$linux_root/drivers/video/fbdev/Kconfig" "$config_stash/fbdev-Kconfig"
fi
if [[ "$usb_console" == 1 ]]; then
	[[ ! -e "$linux_root/drivers/phy/phy-apple-a6-usb.c" ]]
	cp "$linux_root/drivers/phy/Makefile" "$config_stash/phy-Makefile"
	cp "$linux_root/drivers/usb/dwc2/params.c" "$config_stash/dwc2-params.c"
	cp "$linux_root/drivers/usb/dwc2/platform.c" "$config_stash/dwc2-platform.c"
	cp "$linux_root/drivers/usb/dwc2/gadget.c" "$config_stash/dwc2-gadget.c"
	cp "$linux_root/drivers/usb/gadget/udc/core.c" "$config_stash/udc-core.c"
	cp "$linux_root/drivers/usb/gadget/legacy/serial.c" "$config_stash/gadget-serial.c"
	if [[ "${A6_USB_BUS_POWERED:-0}" == 1 ]]; then
	    [[ "${A6_USB_NETWORK:-0}" == 1 ]]
	    cp "$linux_root/drivers/usb/gadget/legacy/cdc2.c" "$config_stash/gadget-cdc2.c"
	fi
fi

if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
    cp "$linux_root/drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c" "$config_stash/brcmfmac-usb.c"
    cp "$linux_root/arch/arm/mm/init.c" "$config_stash/native-arm-mm-init.c"
    [[ ! -e "$linux_root/drivers/net/wireless/broadcom/brcm80211/brcmfmac/a6_hsic.h" ]]
fi
restore_source_tree() {
	status=$?
    if [[ "$status" == 0 && "${A6_INCREMENTAL_BUILD:-0}" == 1 ]]; then
        python3 "$repo_root/scripts/a6-kbuild-cache.py" commit "$linux_root" "$output_root" || status=$?
    fi
	trap - EXIT HUP INT TERM
    for audio_include_name in "${audio_include_names[@]}"; do
        audio_include_path="$linux_root/drivers/video/fbdev/$audio_include_name"
        if [[ -f "$config_stash/$audio_include_name" ]]; then
            cp -p "$config_stash/$audio_include_name" "$audio_include_path"
            rm -f "$config_stash/$audio_include_name"
        else
            rm -f "$audio_include_path"
        fi
    done
    if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
        cp "$config_stash/brcmfmac-usb.c" "$linux_root/drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c"
        cp "$config_stash/native-arm-mm-init.c" "$linux_root/arch/arm/mm/init.c"
        rm -f "$linux_root/drivers/net/wireless/broadcom/brcm80211/brcmfmac/a6_hsic.h"
    fi
    if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
        for name in ehci.h ehci-hub.c ehci-hcd.c Makefile; do
            cp "$config_stash/ehci-$name" "$linux_root/drivers/usb/host/$name"
            rm -f "$config_stash/ehci-$name"
        done
        rm -f "$linux_root/drivers/usb/host/ehci-a6-trial.c" "$linux_root/drivers/usb/host/a6-wifi-usb-download.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-runtime.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-preflight.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-bulk-rx.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-loopback.inc" "$linux_root/drivers/usb/host/brcmfmac-a6-hsic.h" "$linux_root/drivers/usb/host/a6-wifi-usb-scan.inc" "$linux_root/drivers/usb/host/a6-wifi-scan-codec.h"
    fi
	if (( stashed_config )); then
		mv -- "$config_stash/config" "$linux_root/.config"
	fi
	if (( stashed_config_dir )); then
		mv -- "$config_stash/config-dir" "$linux_root/include/config"
	fi
	cp -- "$config_stash/head.S" "$compressed_head"
	cp -- "$config_stash/kernel-head.S" "$kernel_head"
	cp -- "$config_stash/kernel-head-common.S" "$kernel_head_common"
	cp -- "$config_stash/kernel-main.c" "$kernel_main"
	cp -- "$config_stash/kernel-setup.c" "$kernel_setup"
	cp -- "$config_stash/kernel-mmu.c" "$kernel_mmu"
	cp -- "$config_stash/kernel-tlbflush.h" "$kernel_tlb_header"
	cp -- "$config_stash/kernel-tlb-v7.S" "$kernel_tlb_v7"
	cp -- "$config_stash/kernel-smp-plat.h" "$kernel_smp_plat"
	cp -- "$config_stash/kernel-smp.c" "$kernel_smp_source"
	cp -- "$config_stash/kernel-cpuhotplug.h" "$kernel_cpuhotplug_header"
	cp -- "$config_stash/kernel-read-write.c" "$kernel_read_write"
	cp -- "$config_stash/kernel-entry-common.S" "$kernel_entry_common"
	cp -- "$config_stash/kernel-context.c" "$kernel_context"
	cp -- "$config_stash/kernel-traps.c" "$kernel_traps"
	cp -- "$config_stash/kernel-fault.c" "$kernel_fault"
	cp -- "$config_stash/kernel-exec.c" "$kernel_exec"
	cp -- "$config_stash/kernel-binfmt-elf.c" "$kernel_elf"
	cp -- "$config_stash/kernel-samsung-tty.c" "$kernel_uart"
	cp -- "$config_stash/irqchip-Makefile" "$irqchip_makefile"
	cp -- "$config_stash/irqchip-Kconfig" "$irqchip_kconfig"
	cp -- "$config_stash/clocksource-Makefile" "$clocksource_makefile"
	if (( usb_sources_installed )); then
		cp -- "$config_stash/phy-Makefile" "$linux_root/drivers/phy/Makefile"
		cp -- "$config_stash/dwc2-params.c" "$linux_root/drivers/usb/dwc2/params.c"
		cp -- "$config_stash/dwc2-platform.c" "$linux_root/drivers/usb/dwc2/platform.c"
		cp -- "$config_stash/dwc2-gadget.c" "$linux_root/drivers/usb/dwc2/gadget.c"
		cp -- "$config_stash/udc-core.c" "$linux_root/drivers/usb/gadget/udc/core.c"
		cp -- "$config_stash/gadget-serial.c" "$linux_root/drivers/usb/gadget/legacy/serial.c"
		rm -f -- "$linux_root/drivers/phy/phy-apple-a6-usb.c"
	fi
	if (( usb_power_descriptor_patched )); then
		cp -- "$config_stash/gadget-cdc2.c" "$linux_root/drivers/usb/gadget/legacy/cdc2.c"
		rm -f -- "$config_stash/gadget-cdc2.c"
	fi
	rm -f -- "$a6_irqchip" "$a6_timer"
    if [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        rm -f -- "$linux_root/drivers/irqchip/a6-smp.c" \
            "$linux_root/drivers/irqchip/a6-smp-layout.h" \
            "$linux_root/drivers/irqchip/a6-smp-bridge-blob.h" \
            "$linux_root/drivers/irqchip/a6-smp-shootdown.inc"
    fi
    if (( fb_sources_installed )); then
        cp "$config_stash/fbdev-Makefile" "$linux_root/drivers/video/fbdev/Makefile"
        cp "$config_stash/fbdev-Kconfig" "$linux_root/drivers/video/fbdev/Kconfig"
        rm -f "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then
        cp "$config_stash/simpledrm.c" "$linux_root/drivers/gpu/drm/sysfb/simpledrm.c"
    fi
	rmdir "$config_stash" 2>/dev/null || true
	exit "$status"
}

if [[ -e "$linux_root/.config" ]]; then
	mv -- "$linux_root/.config" "$config_stash/config"
	stashed_config=1
fi
if [[ -d "$linux_root/include/config" ]]; then
	mv -- "$linux_root/include/config" "$config_stash/config-dir"
	stashed_config_dir=1
fi
trap restore_source_tree EXIT HUP INT TERM
if [[ "${A6_USB_BUS_POWERED:-0}" == 1 ]]; then
    python3 - "$linux_root/drivers/usb/gadget/legacy/cdc2.c" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
old = '\t.bmAttributes\t\t= USB_CONFIG_ATT_SELFPOWER,\n'
assert s.count(old) == 1
s = s.replace(old, '\t.bmAttributes\t\t= USB_CONFIG_ATT_ONE,\n\t.MaxPower\t\t= 500,\n')
p.write_text(s)
PY
    usb_power_descriptor_patched=1
fi
if [[ "${A6_FRAMEBUFFER:-0}" == 1 ]]; then
    fb_sources_installed=1
    cp "$repo_root/kernel/platform/fb-apple-a6.c" "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    if [[ "${A6_WIFI_CLOCK_SNAPSHOT:-0}" == 1 ]]; then
        cat "$repo_root/kernel/platform/a6-wifi-clock-snapshot.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_WIFI_EHCI_CAPS:-0}" == 1 ]]; then
        [[ "${A6_WIFI_CLOCK_SNAPSHOT:-0}" == 1 ]]
        cat "$repo_root/kernel/platform/a6-wifi-ehci-caps.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then
        sed -i '1i#define A6_DIRECT_DRM 1' "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        python3 - "$linux_root/drivers/gpu/drm/sysfb/simpledrm.c" "$repo_root/kernel/platform/a6-simpledrm-map.inc" <<'DRMPATCH'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
needle='static const struct drm_driver simpledrm_driver;'
# Place helpers before the first format helper, after upstream includes.
pos=s.index('static const struct drm_format_info *')
s=s[:pos]+Path(sys.argv[2]).read_text()+'\n'+s[pos:]
needle='\t\tscreen_base = devm_ioremap_wc(&pdev->dev, mem->start, resource_size(mem));'
assert s.count(needle)==1
s=s.replace(needle,r"""        if (of_machine_is_compatible("apple,n42ap")) {
            if (mem->start != 0xbf7aa000 || resource_size(mem) != 640 * 1136 * 4 ||
                !a6_drm_mapping_valid(mem->start, resource_size(mem)))
                return ERR_PTR(-EINVAL);
            screen_base = (void __iomem *)(unsigned long)mem->start;
            drm_info(dev, "A6 reuses validated strongly-ordered framebuffer map\n");
        } else {
            screen_base = devm_ioremap_wc(&pdev->dev, mem->start, resource_size(mem));
        }""")
p.write_text(s)
DRMPATCH
    fi
    if [[ "${A6_MEMORY_CAPTURE:-0}" == 1 ]]; then
        cat "$repo_root/kernel/platform/a6-memory-capture.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_USB_RECONNECT_SCREEN:-0}" == 1 ]]; then
        [[ "${A6_DIRECT_DRM:-0}" == 1 && "$usb_console" == 1 ]]
        if [[ "${A6_USB_RECONNECT_EP0:-0}" == 1 ]]; then
            printf '#define A6_USB_RECONNECT_EP0 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_USB_RECONNECT_PHY:-0}" == 1 ]]; then
            [[ "${A6_USB_RECONNECT_EP0:-0}" != 1 ]]
            printf '#define A6_USB_RECONNECT_PHY 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_USB_RECONNECT_VBUS_LATCH:-0}" == 1 ]]; then
            [[ "${A6_USB_RECONNECT_PHY:-0}" == 1 && "${A6_D1972_POLICY:-0}" == 1 && "${A6_USB_RECONNECT_ENUM_REARM:-0}" != 1 ]]
            printf '#define A6_USB_RECONNECT_VBUS_LATCH 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_USB_CORE_RESET_TRACE:-0}" == 1 ]]; then
            [[ "${A6_USB_RECONNECT_VBUS_LATCH:-0}" == 1 ]]
            printf '#define A6_USB_CORE_RESET_TRACE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_USB_CORE_STAGE_TRACE:-0}" == 1 ]]; then
            [[ "${A6_USB_CORE_RESET_TRACE:-0}" == 1 ]]
            printf '#define A6_USB_CORE_STAGE_TRACE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_USB_RECONNECT_LX_LATCH:-0}" == 1 ]]; then
            [[ "${A6_USB_RECONNECT_PHY:-0}" == 1 && "${A6_USB_RECONNECT_VBUS_LATCH:-0}" != 1 && "${A6_USB_RECONNECT_ENUM_REARM:-0}" != 1 ]]
            printf '#define A6_USB_RECONNECT_LX_LATCH 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        cat "$repo_root/kernel/platform/a6-usb-reconnect-screen.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_BATTERY_OBSERVER:-0}" == 1 ]]; then
        [[ "${A6_DIRECT_DRM:-0}" == 1 && "${A6_MEMORY_CAPTURE:-0}" == 1 ]]
        cat "$repo_root/kernel/platform/a6-battery-observer.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_BATTERY_HDQ_READ:-0}" == 1 ]]; then
        [[ "${A6_DIRECT_DRM:-0}" == 1 && "${A6_MEMORY_CAPTURE:-0}" == 1 && "${A6_BATTERY_OBSERVER:-0}" == 0 ]]
        if [[ "${A6_HDQ_LINE_OBSERVER:-0}" == 1 ]]; then
            printf '%s\n' '#define A6_HDQ_LINE_OBSERVER 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_HDQ_PHASE_OBSERVER:-0}" == 1 ]]; then
            [[ "${A6_HDQ_LINE_OBSERVER:-0}" == 1 && "${A6_D1972_VBAT_MONITOR:-0}" == 1 ]]
            printf '%s\n' '#define A6_HDQ_PHASE_OBSERVER 1' '#define A6_HDQ_WITH_VBAT_MONITOR 1' '#include <linux/ktime.h>' '#include <linux/math64.h>' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            if [[ "${A6_HDQ_REALTIME_US:-0}" == 1 ]]; then
                printf '%s\n' '#define A6_HDQ_REALTIME_US 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                if [[ "${A6_HDQ_ECHO_GUARD:-0}" == 1 ]]; then
                    printf '%s\n' '#define A6_HDQ_ECHO_GUARD 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_HDQ_TX_TURNAROUND:-0}" == 1 ]]; then
                        printf '%s\n' '#define A6_HDQ_TX_TURNAROUND 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                fi
            fi
        fi
        cat "$repo_root/kernel/platform/a6-battery-hdq-read.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
    fi
    if [[ "${A6_TOUCH_TRANSPORT:-0}" == 1 ]]; then
        [[ "${A6_DIRECT_DRM:-0}" == 1 && "${A6_MEMORY_CAPTURE:-0}" == 1 ]]
        cat "$repo_root/kernel/platform/a6-touch-transport.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        if [[ "${A6_TOUCH_CLOCK:-0}" == 1 ]]; then
            cat "$repo_root/kernel/platform/a6-touch-clock.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
        fi
        if [[ "${A6_TOUCH_I2C:-0}" == 1 ]]; then
            [[ "${A6_TOUCH_CHECK:-0}" == 0 || "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]
            cat "$repo_root/kernel/platform/a6-touch-i2c.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            if [[ "${A6_TOUCH_PMU_READ:-0}" == 1 ]]; then
                cat "$repo_root/kernel/platform/a6-touch-pmu-read.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            fi
        fi
        if [[ "${A6_TOUCH_CHECK:-0}" == 1 ]]; then
            if [[ "${A6_TOUCH_PWM_CHECK:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_CLOCK:-0}" == 1 && "${A6_CAPTURE_CPU_CLOCK:-0}" == 1 ]]
                cat "$repo_root/kernel/platform/a6-touch-pwm-check.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            fi
            if [[ "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_I2C:-0}" == 1 && "${A6_TOUCH_PWM_CHECK:-0}" == 1 && "${A6_TOUCH_PMU_READ:-0}" == 0 ]]
                if [[ "${A6_CHARGER_PROOF:-0}" == 1 ]]; then
                    printf '%s\n' '#define A6_CHARGER_PROOF 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_CHARGER_ACTIVE_TRIAL:-0}" == 1 ]]; then
                    [[ "${A6_CHARGER_PROOF:-0}" == 1 && "${A6_USB_BUS_POWERED:-0}" == 1 ]]
                    printf '%s\n' '#define A6_CHARGER_ACTIVE_TRIAL 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]; then
                    printf '%s\n' '#define A6_D1972_VBUS_ADC 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_D1972_POLICY:-0}" == 1 ]]; then
                    [[ "${A6_D1972_TBAT_ADC:-0}" == 1 && "${A6_D1972_VBAT_MONITOR:-0}" == 1 && "${A6_USB_BUS_POWERED:-0}" == 1 ]]
                    printf '%s\n' '#define A6_D1972_POLICY 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_D1972_STOCK_OFF_CANDIDATE:-0}" == 1 ]]; then
                        printf '%s\n' '#define A6_D1972_STOCK_OFF_CANDIDATE 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                    if [[ "${A6_D1972_LOW_BATTERY_CANDIDATE:-0}" == 1 ]]; then
                        [[ "${A6_D1972_STOCK_OFF_CANDIDATE:-0}" == 1 ]]
                        printf '%s\n' '#define A6_D1972_LOW_BATTERY_CANDIDATE 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        if [[ "${A6_D1972_BOOT_DEFAULTS:-0}" == 1 ]]; then
                            printf '%s\n' '#define A6_D1972_BOOT_DEFAULTS 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        fi
                        if [[ "${A6_LOW_BATTERY_TRACE_SCREEN:-0}" == 1 ]]; then
                            [[ "${A6_DIRECT_DRM:-0}" == 1 ]]
                            printf '%s\n' '#define A6_LOW_BATTERY_TRACE_SCREEN 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        fi
                    fi
                fi
                if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
                    printf '%s\n' '#define A6_WIFI_EHCI_ENUM 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                cat "$repo_root/kernel/platform/a6-touch-power-check.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                if [[ "${A6_CHARGER_PROOF:-0}" == 1 && "${A6_D1972_POLICY:-0}" != 1 ]]; then
                    cat "$repo_root/kernel/platform/a6-charger-proof.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_D1972_POWER_SUPPLY:-0}" == 1 ]]; then
                    [[ "${A6_CHARGER_PROOF:-0}" == 1 ]]
                    printf '%s\n' '#include <linux/power_supply.h>' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    cat "$repo_root/kernel/platform/a6-d1972-power-supply.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]; then
                    [[ "${A6_CHARGER_PROOF:-0}" == 1 ]]
                    cat "$repo_root/kernel/platform/a6-d1972-vbus-adc.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_D1972_VBAT_ADC:-0}" == 1 ]]; then
                    [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]
                    if [[ "${A6_D1972_VBAT_MONITOR:-0}" == 1 ]]; then
                        printf '%s\n' '#define A6_D1972_VBAT_MONITOR 1' '#include <linux/jiffies.h>' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                    cat "$repo_root/kernel/platform/a6-d1972-vbat-adc.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_D1972_VBAT_MONITOR:-0}" == 1 ]]; then
                        cat "$repo_root/kernel/platform/a6-d1972-battery-supply.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                fi
                if [[ "${A6_D1972_TBAT_ADC:-0}" == 1 ]]; then
                    [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]
                    cat "$repo_root/kernel/platform/a6-d1972-tbat-adc.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_D1972_POLICY:-0}" == 1 ]]; then
                    cat "$repo_root/kernel/platform/a6-d1972-policy.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_AUDIO_FIFO_DISCOVER:-0}" == 1 ]]; then
                        [[ "${A6_AUDIO_GATE_OBSERVE:-0}" != 1 ]]
                        if [[ "${A6_AUDIO_AMP_ID:-0}" == 1 ]]; then printf '\n#define A6_AUDIO_AMP_ID 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"; fi
                        if [[ "${A6_AUDIO_TONE:-0}" == 1 ]]; then
                            [[ "${A6_AUDIO_AMP_ID:-0}" == 1 && "${A6_CAPTURE_AUDIO:-0}" == 1 ]]
                            printf '\n#define A6_AUDIO_TONE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                            cat "$repo_root/build/audio-research/codec-receiver-sequence.private.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                            cat "$repo_root/build/audio-research/amp-tone-sequence.private.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                            cp "$repo_root/kernel/platform/a6-audio-tone.inc" "$linux_root/drivers/video/fbdev/a6-audio-tone.inc"
                            cp "$repo_root/kernel/platform/a6-audio-codec-play.inc" "$linux_root/drivers/video/fbdev/a6-audio-codec-play.inc"
                            cp "$repo_root/kernel/platform/a6-audio-codec.inc" "$linux_root/drivers/video/fbdev/a6-audio-codec.inc"
                        fi
                        if [[ "${A6_AUDIO_ALSA:-0}" == 1 ]]; then
                            if [[ "${A6_AUDIO_RAW_CAPTURE:-0}" == 1 ]]; then printf '\n#define A6_AUDIO_RAW_CAPTURE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"; fi
                            printf '\n#define A6_AUDIO_ALSA 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        fi
                        cat "$repo_root/kernel/platform/a6-audio-fifo-discover.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        if [[ "${A6_AUDIO_ALSA:-0}" == 1 ]]; then
                            [[ "${A6_AUDIO_TONE:-0}" == 1 ]]
                            cat "$repo_root/build/audio-research/mic-recording-sequence.private.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                            cp "$repo_root/kernel/platform/a6-audio-alsa.inc" "$linux_root/drivers/video/fbdev/a6-audio-alsa.inc"
                            printf '\n#include "a6-audio-alsa.inc"\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        fi
                    fi
                    if [[ "${A6_AUDIO_GATE_OBSERVE:-0}" == 1 ]]; then
                        cat "$repo_root/kernel/platform/a6-audio-gate-observe.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                    if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
                        if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then printf '\n#define A6_WIFI_NATIVE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"; fi
                        cat "$repo_root/kernel/platform/a6-wifi-ehci-enum.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                fi
                if [[ "${A6_CPU1_PREFLIGHT:-0}" == 1 ]]; then
                    if [[ "${A6_CPU1_ALIAS_PREFLIGHT:-0}" == 1 ]]; then
                        printf '#define A6_CPU1_ALIAS_PREFLIGHT 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                    cat "$repo_root/kernel/platform/a6-cpu1-preflight.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_CPU1_ALIAS_PREFLIGHT:-0}" == 1 ]]; then
                        if [[ "${A6_CPU1_ALIAS_WRITE:-0}" == 1 ]]; then
                            printf '#define A6_CPU1_ALIAS_WRITE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                            cat "$repo_root/kernel/platform/a6-cpu1-alias-write.inc" > "$output_root/a6-cpu1-alias-write.inc"
                        fi
                        if [[ "${A6_CPU1_ENTRY_PROBE:-0}" == 1 ]]; then
                            extra_object=()
                            if [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]; then
                                cpu1_extended_source="$repo_root/boot/arm/a6-cpu1-tlbi-probe.S"
                                if [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]; then
                                    cpu1_extended_source="$repo_root/boot/arm/a6-cpu1-cache-probe.S"
                                fi
                                cache_tre_define=()
                                if [[ "${A6_CPU1_CACHE_TRE_PROBE:-0}" == 1 ]]; then
                                    cache_tre_define=(-DA6_CPU1_CACHE_TRE_PROBE=1)
                                fi
                                clang --target=arm-none-eabi -mcpu=swift -marm -ffreestanding -nostdlib "${cache_tre_define[@]}" -c "$cpu1_extended_source" -o "$output_root/a6-cpu1-tlbi-probe.o"
                                ! llvm-readelf -r "$output_root/a6-cpu1-tlbi-probe.o" | rg -q 'R_ARM'
                                llvm-objcopy -O binary --only-section=.text.cpu1_tlbi "$output_root/a6-cpu1-tlbi-probe.o" "$output_root/a6-cpu1-tlbi-probe.bin"
                                python3 "$repo_root/scripts/a6-cpu1-tlbi-blob.py" "$output_root/a6-cpu1-tlbi-probe.bin" "$output_root/a6-cpu1-tlbi-blob.inc"
                                if [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]; then
                                    cp "$repo_root/kernel/platform/a6-cpu1-cache-layout.inc" "$output_root/a6-cpu1-cache-layout.inc"
                                    cp "$repo_root/kernel/platform/a6-cpu1-cache-map.inc" "$output_root/a6-cpu1-cache-map.inc"
                                    cp "$repo_root/kernel/platform/a6-cpu1-cache-test.inc" "$output_root/a6-cpu1-cache-test.inc"
                                    printf '#define A6_CPU1_CACHE_PROBE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                    if [[ "${A6_CPU1_CACHE_TRE_PROBE:-0}" == 1 ]]; then
                                        printf '#define A6_CPU1_CACHE_TRE_PROBE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                    fi
                                    if [[ "${A6_CPU1_CACHE_REPEAT_PROBE:-0}" == 1 ]]; then
                                        printf '#define A6_CPU1_CACHE_REPEAT_PROBE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                    fi
                                    if [[ "${A6_CPU1_CACHE_SHAREABLE_PROBE:-0}" == 1 ]]; then
                                        printf '#define A6_CPU1_CACHE_SHAREABLE_PROBE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                    fi
                                else
                                    cp "$repo_root/kernel/platform/a6-cpu1-tlbi-layout.inc" "$output_root/a6-cpu1-tlbi-layout.inc"
                                    cp "$repo_root/kernel/platform/a6-cpu1-tlbi-test.inc" "$output_root/a6-cpu1-tlbi-test.inc"
                                fi
                                printf '#define A6_CPU1_TLBI_PROBE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                extra_object+=("$output_root/a6-cpu1-tlbi-probe.o")
                            fi
                            A6_CPU1_MARKER_PA=0x83ffe200 bash "$repo_root/scripts/build-a6-cpu1-entry-probe.sh" > "$output_root/cpu1-probe-compile.log"
                            python3 "$repo_root/scripts/a6-cpu1-probe-blob.py" "$repo_root/build/arm/a6-cpu1-entry-probe.bin" "$output_root/a6-cpu1-entry-blob.inc" "$repo_root/build/arm/a6-cpu1-entry-probe.o" "${extra_object[@]}"
                            cp "$repo_root/kernel/platform/a6-cpu1-entry-probe.inc" "$output_root/a6-cpu1-entry-probe.inc"
                            if [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]; then
                                cp "$repo_root/kernel/platform/a6-cpu1-ipi-probe.inc" "$output_root/a6-cpu1-ipi-probe.inc"
                            fi
                            printf '#define A6_CPU1_ENTRY_PROBE 1\n' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        fi
                        sed -e "s|#include \"a6-cpu1-alias-write.inc\"|#include \"$output_root/a6-cpu1-alias-write.inc\"|" -e "s|#include \"a6-cpu1-entry-probe.inc\"|#include \"$output_root/a6-cpu1-entry-probe.inc\"|" "$repo_root/kernel/platform/a6-cpu1-alias-preflight.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                fi
                if [[ "${A6_BACKLIGHT_TRIAL:-0}" == 1 ]]; then
                    [[ "${A6_D1972_VBAT_MONITOR:-0}" == 1 && "${A6_USB_BUS_POWERED:-0}" == 1 ]]
                    cat "$repo_root/kernel/platform/a6-backlight-trial.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
            fi
            if [[ "${A6_TOUCH_GPIO_CS:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]
                printf '%s\n' '#define A6_TOUCH_GPIO_CS 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            fi
            if [[ "${A6_TOUCH_N1_VERSION:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_GPIO_CS:-0}" == 1 && "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]
                printf '%s\n' '#define A6_TOUCH_N1_VERSION 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            fi
            if [[ "${A6_TOUCH_N1_START_VERSION:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_GPIO_CS:-0}" == 1 && "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]
                printf '%s\n' '#define A6_TOUCH_N1_START_VERSION 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            fi
            if [[ "${A6_TOUCH_HBPP:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_GPIO_CS:-0}" == 1 ]]
                printf '%s\n' '#define A6_TOUCH_HBPP 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            fi
            cat "$repo_root/kernel/platform/a6-touch-check.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
            if [[ "${A6_TOUCH_FW_UPLOAD:-0}" == 1 ]]; then
                [[ "${A6_TOUCH_HBPP:-0}" == 1 && "${A6_TOUCH_GPIO_CS:-0}" == 1 && "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]
                python3 "$repo_root/scripts/prepare-a6-touch-packet.py" > "$repo_root/build/touch-fw-packet-audit.json"
                python3 - "$repo_root/build/touch-research/N42-constructed-firmware.bin" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c" <<'PACKET'
from pathlib import Path
import sys
data = Path(sys.argv[1]).read_bytes()
if len(data) != 64340:
    raise SystemExit('N42 packet length changed')
print('static const u8 a6_n42_fw_packet[] = {')
for i in range(0, len(data), 16):
    print('\t' + ', '.join(f'0x{b:02x}' for b in data[i:i+16]) + ',')
print('};')
PACKET
                if [[ "${A6_TOUCH_POST_UPLOAD:-0}" == 1 ]]; then
                    printf '%s\n' '#define A6_TOUCH_POST_UPLOAD 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_TOUCH_CLK32_ENABLE:-0}" == 1 ]]; then
                        [[ "${A6_TOUCH_CALIBRATION:-0}" == 1 && "${A6_TOUCH_E2_RETRY:-0}" == 1 ]]
                        printf '%s\n' '#define A6_TOUCH_CLK32_ENABLE 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                fi
                if [[ "${A6_TOUCH_CALIBRATION:-0}" == 1 ]]; then
                    [[ "${A6_TOUCH_REPORT_PROBE:-0}" == 1 && "${A6_TOUCH_CORRECT_EXEC_ADDR:-0}" == 1 ]]
                    python3 "$repo_root/scripts/prepare-a6-n42-calibration.py" > "$repo_root/build/touch-research/n42-calibration-preparation.json"
                    printf '%s\n' '#define A6_TOUCH_CALIBRATION 1' '#define A6_TOUCH_CORRECT_EXEC_ADDR 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    cat "$repo_root/build/touch-research/n42-calibration-packets.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_TOUCH_REPORT_PROBE:-0}" == 1 ]]; then
                    [[ "${A6_TOUCH_POST_UPLOAD:-0}" == 1 ]]
                    printf '%s\n' '#define A6_TOUCH_REPORT_PROBE 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_TOUCH_E2_RETRY:-0}" == 1 ]]; then
                        [[ "${A6_TOUCH_CALIBRATION:-0}" == 1 ]]
                        printf '%s\n' '#define A6_TOUCH_E2_RETRY 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    fi
                    if [[ "${A6_TOUCH_E3_INFO:-0}" == 1 ]]; then
                        [[ "${A6_TOUCH_CLK32_ENABLE:-0}" == 1 && "${A6_TOUCH_E2_RETRY:-0}" == 1 ]]
                        printf '%s\n' '#define A6_TOUCH_E3_INFO 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        if [[ "${A6_TOUCH_REPORT_METADATA:-0}" == 1 ]]; then
                            printf '%s\n' '#define A6_TOUCH_REPORT_METADATA 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                            if [[ "${A6_TOUCH_FRAME_CAPTURE:-0}" == 1 ]]; then
                                printf '%s\n' '#define A6_TOUCH_FRAME_CAPTURE 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                if [[ "${A6_TOUCH_NATIVE_INPUT:-0}" == 1 ]]; then
                                    printf '%s\n' '#define A6_TOUCH_NATIVE_INPUT 1' >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                                fi
                            fi
                        fi
                    fi
                fi
                cat "$repo_root/kernel/platform/a6-touch-fw-upload.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                if [[ "${A6_TOUCH_POST_UPLOAD:-0}" == 1 ]]; then
                    cat "$repo_root/kernel/platform/a6-touch-post-upload.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_TOUCH_CALIBRATION:-0}" == 1 ]]; then
                    cat "$repo_root/kernel/platform/a6-touch-calibration.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                fi
                if [[ "${A6_TOUCH_REPORT_PROBE:-0}" == 1 ]]; then
                    cat "$repo_root/kernel/platform/a6-touch-report-probe.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                    if [[ "${A6_TOUCH_FRAME_CAPTURE:-0}" == 1 ]]; then
                        cat "$repo_root/kernel/platform/a6-touch-frame-capture.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        if [[ "${A6_TOUCH_NATIVE_INPUT:-0}" == 1 ]]; then
                            cat "$repo_root/kernel/platform/a6-touch-native-input.inc" >> "$linux_root/drivers/video/fbdev/fb-apple-a6.c"
                        fi
                    fi
                fi
            fi
        fi
    fi
    printf '%s\n' 'obj-$(CONFIG_FB_A6_BOOT) += fb-apple-a6.o' >> "$linux_root/drivers/video/fbdev/Makefile"
    cat >> "$linux_root/drivers/video/fbdev/Kconfig" <<'EOF'

config FB_A6_BOOT
    bool "Apple A6 inherited boot framebuffer"
    depends on FB=y && ARM && !ARM_LPAE
    select FB_IOMEM_FOPS

config A6_AUDIO_ALSA
    bool "N42 PIO ALSA candidate"
    depends on FB_A6_BOOT && SND=y
    select SND_PCM
    select SND_TIMER
EOF
fi

# ARCH_APPLE exists only under arm64. Include the existing S5L data for
# this ARM32 bring-up profile without pretending to enable that platform.
patch --batch --forward -d "$linux_root" -p1 < "$repo_root/kernel/patches/a6-s5l-uart-data.patch"
if [[ "$usb_console" == 1 ]]; then
	usb_sources_installed=1
	patch --batch --forward -d "$linux_root" -p1 < "$repo_root/kernel/patches/a6-dwc2-pio.patch"
	patch --batch --forward -d "$linux_root" -p1 < "$repo_root/kernel/patches/a6-dwc2-l3-reinit.patch"
	if [[ "${A6_USB_VBUS_BRIDGE:-0}" == 1 ]]; then
	    [[ "${A6_D1972_POLICY:-0}" == 1 ]]
	    python3 - "$linux_root/drivers/usb/dwc2/platform.c" "$repo_root/kernel/platform/a6-dwc2-vbus-bridge.inc" <<'VBUSBRIDGE'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
source = path.read_text()
bridge = ("#define A6_USB_BVALID_OVERRIDE 1\n"
          if os.environ.get("A6_USB_BVALID_OVERRIDE") == "1" else "")
bridge += ("#define A6_USB_VBUS_AUTO_RECOVER 1\n"
           if os.environ.get("A6_USB_VBUS_AUTO_RECOVER") == "1" else "")
bridge += Path(sys.argv[2]).read_text()

def insert(anchor, addition):
    global source
    assert source.count(anchor) == 1, anchor
    source = source.replace(anchor, anchor + addition)

insert('static const char dwc2_driver_name[] = "dwc2";\n', '\n' + bridge)
insert('struct dwc2_hsotg *hsotg = platform_get_drvdata(dev);\n'
       '\tstruct dwc2_gregs_backup *gr;\n'
       '\tint ret = 0;\n',
       '\n\ta6_vbus_bridge_stop(hsotg);\n')
anchor = ('\t\t\tdwc2_hsotg_remove(hsotg);\n'
          '\t\t\tgoto error_debugfs;\n'
          '\t\t}\n')
assert source.count(anchor) == 1, anchor
source = source.replace(anchor, anchor + '\t\ta6_vbus_bridge_start(hsotg);\n')
path.write_text(source)
VBUSBRIDGE
	    if [[ "${A6_USB_VBUS_AUTO_RECOVER:-0}" == 1 ]]; then
		python3 - "$linux_root/drivers/usb/gadget/udc/core.c" "$repo_root/kernel/platform/a6-usb-udc-cycle.inc" <<'UDCCYCLE'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
cycle = Path(sys.argv[2]).read_text()
if cycle in source:
    raise SystemExit(0)
include = '#include <linux/workqueue.h>\n'
assert source.count(include) == 1
if '#include <linux/delay.h>\n' not in source:
    source = source.replace(include, include + '#include <linux/delay.h>\n')
anchor = 'static ssize_t soft_connect_store(struct device *dev,\n'
assert source.count(anchor) == 1
source = source.replace(anchor, cycle + '\n' + anchor)
path.write_text(source)
UDCCYCLE
	    fi
	fi
	if [[ "${A6_USB_RECONNECT_SCREEN:-0}" == 1 ]]; then
	    python3 - "$linux_root/drivers/usb/dwc2/gadget.c" "$repo_root/kernel/platform/a6-dwc2-lx-latch.inc" <<'TRACE'
from pathlib import Path
import os
import sys
p = Path(sys.argv[1])
s = p.read_text()
def insert(after, addition):
    global s
    assert s.count(after) == 1, after
    s = s.replace(after, after + addition)
insert('return container_of(gadget, struct dwc2_hsotg, gadget);\n}',
       '\n/* N42 diagnostic counters; only this image defines the observer. */\n'
       'u32 a6_usb_reconnect_trace[' +
       ('18' if os.environ.get('A6_USB_RECONNECT_EP0') == '1' or
       os.environ.get('A6_USB_RECONNECT_PHY') == '1' else '9') + '];\n')
if os.environ.get('A6_USB_CORE_RESET_TRACE') == '1':
    insert('u32 a6_usb_reconnect_trace[18];',
           '\nu32 a6_usb_core_reset_trace[' +
           ('10' if os.environ.get('A6_USB_CORE_STAGE_TRACE') == '1' else '3') +
           '];\n')
    old = ('\t\tif (dwc2_core_reset(hsotg, true))\n'
           '\t\t\treturn;')
    assert s.count(old) == 1, old
    s = s.replace(old,
        '\t\t{\n'
        '\t\t\tint reset_ret = dwc2_core_reset(hsotg, true);\n'
        '\t\t\tWRITE_ONCE(a6_usb_core_reset_trace[0], '
        'READ_ONCE(a6_usb_core_reset_trace[0]) + 1);\n'
        '\t\t\tWRITE_ONCE(a6_usb_core_reset_trace[1], (u32)reset_ret);\n'
        '\t\t\tWRITE_ONCE(a6_usb_core_reset_trace[2], '
        'dwc2_readl(hsotg, GRSTCTL));\n'
        '\t\t\tif (reset_ret)\n'
        '\t\t\t\treturn;\n'
        '\t\t}')
if os.environ.get('A6_USB_CORE_STAGE_TRACE') == '1':
    insert('u32 a6_usb_core_reset_trace[10];',
           '\nstatic u32 a6_usb_stage_history[4][5];\n'
           'static ssize_t a6_usb_stage_show(struct device *dev, '
           'struct device_attribute *attr, char *buf)\n'
           '{\n'
           '\tu32 count = smp_load_acquire(&a6_usb_core_reset_trace[9]);\n'
           '\tu32 i;\n'
           '\tint len;\n'
           '\tlen = sysfs_emit(buf, "resets=%u reset_ret=%d pullup_connects=%u\\n",\n'
           '\t\tREAD_ONCE(a6_usb_core_reset_trace[0]), '
           '(s32)READ_ONCE(a6_usb_core_reset_trace[1]), count);\n'
           '\tfor (i = 0; i < count && i < 4; i++)\n'
           '\t\tlen += sysfs_emit_at(buf, len, "event=%u intended=%08x '
           'immediate=%08x after=%08x gotgctl=%08x reset_ret=%d\\n",\n'
           '\t\t\ti, READ_ONCE(a6_usb_stage_history[i][0]),\n'
           '\t\t\tREAD_ONCE(a6_usb_stage_history[i][1]),\n'
           '\t\t\tREAD_ONCE(a6_usb_stage_history[i][2]),\n'
           '\t\t\tREAD_ONCE(a6_usb_stage_history[i][3]),\n'
           '\t\t\t(s32)READ_ONCE(a6_usb_stage_history[i][4]));\n'
           '\treturn len;\n'
           '}\n'
           'static DEVICE_ATTR_RO(a6_usb_stage);\n'
           'static struct attribute *a6_usb_stage_attrs[] = {\n'
           '\t&dev_attr_a6_usb_stage.attr, NULL,\n'
           '};\n'
           'static const struct attribute_group a6_usb_stage_group = {\n'
           '\t.attrs = a6_usb_stage_attrs,\n'
           '};\n')
    insert('\tdwc2_writel(hsotg, intmsk, GINTMSK);',
           '\n\tWRITE_ONCE(a6_usb_core_reset_trace[2], intmsk);'
           '\n\tWRITE_ONCE(a6_usb_core_reset_trace[3], '
           'dwc2_readl(hsotg, GINTMSK));')
    insert('\t\thsotg->enabled = 1;\n'
           '\t\tdwc2_hsotg_core_init_disconnected(hsotg, false);',
           '\n\t\tWRITE_ONCE(a6_usb_core_reset_trace[5], '
           'READ_ONCE(a6_usb_core_reset_trace[2]));'
           '\n\t\tWRITE_ONCE(a6_usb_core_reset_trace[6], '
           'READ_ONCE(a6_usb_core_reset_trace[3]));'
           '\n\t\tWRITE_ONCE(a6_usb_core_reset_trace[7], '
           'dwc2_readl(hsotg, GINTMSK));'
           '\n\t\tWRITE_ONCE(a6_usb_core_reset_trace[8], '
           'dwc2_readl(hsotg, GOTGCTL));'
           '\n\t\t{\n'
           '\t\t\tu32 event = READ_ONCE(a6_usb_core_reset_trace[9]);\n'
           '\t\t\tif (event < 4) {\n'
           '\t\t\t\tWRITE_ONCE(a6_usb_stage_history[event][0], '
           'READ_ONCE(a6_usb_core_reset_trace[5]));\n'
           '\t\t\t\tWRITE_ONCE(a6_usb_stage_history[event][1], '
           'READ_ONCE(a6_usb_core_reset_trace[6]));\n'
           '\t\t\t\tWRITE_ONCE(a6_usb_stage_history[event][2], '
           'READ_ONCE(a6_usb_core_reset_trace[7]));\n'
           '\t\t\t\tWRITE_ONCE(a6_usb_stage_history[event][3], '
           'READ_ONCE(a6_usb_core_reset_trace[8]));\n'
           '\t\t\t\tWRITE_ONCE(a6_usb_stage_history[event][4], '
           'READ_ONCE(a6_usb_core_reset_trace[1]));\n'
           '\t\t\t}\n'
           '\t\t\tsmp_store_release(&a6_usb_core_reset_trace[9], '
           'event + 1);\n'
           '\t\t}')
    old = '\tdwc2_hsotg_dump(hsotg);\n\n\treturn 0;\n}'
    assert s.count(old) == 1, old
    s = s.replace(old,
        '\tdwc2_hsotg_dump(hsotg);'
        '\n\n\tret = devm_device_add_group(dev, &a6_usb_stage_group);'
        '\n\tif (ret)'
        '\n\t\treturn ret;'
        '\n\n\treturn 0;\n}')
if os.environ.get('A6_USB_RECONNECT_LX_LATCH') == '1':
    insert('u32 a6_usb_reconnect_trace[18];',
           '\n' + Path(sys.argv[2]).read_text())
    if os.environ.get('A6_USB_RECONNECT_L3_REARM') == '1':
        reinit_condition = ('(usb_status & GOTGCTL_BSESVLD) && '
                            '(connected || hsotg->lx_state == DWC2_L3)')
    elif os.environ.get('A6_USB_RECONNECT_REARM') == '1':
        reinit_condition = ('(usb_status & GOTGCTL_BSESVLD) && '
                            '(connected || !(dwc2_readl(hsotg, DOEPCTL0) & DXEPCTL_EPENA))')
    else:
        reinit_condition = '(usb_status & GOTGCTL_BSESVLD) && connected'
    insert('u32 connected = hsotg->connected;',
           '\n\t\tif (gintsts & GINTSTS_USBRST) {'
           '\n\t\t\ta6_usb_lx_record_reset(hsotg, usb_status, connected, '
           + reinit_condition + ');'
           '\n\t\t}')
    insert('/* Prevent new request submission when controller is suspended */',
           '\n\tif (hs_ep->index == 0 && hs->lx_state != DWC2_L0)'
           '\n\t\ta6_usb_lx_record_eagain(hs);\n')
    old = '\tdwc2_hsotg_dump(hsotg);\n\n\treturn 0;\n}'
    assert s.count(old) == 1, old
    s = s.replace(old,
        '\tdwc2_hsotg_dump(hsotg);'
        '\n\n\t/* Diagnostic sysfs state follows the platform device lifetime. */'
        '\n\tret = devm_device_add_group(dev, &a6_usb_lx_group);'
        '\n\tif (ret)'
        '\n\t\treturn ret;'
        '\n\n\treturn 0;\n}')
insert('ctrl->wIndex, ctrl->wLength);',
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[3], '
       'READ_ONCE(a6_usb_reconnect_trace[3]) + 1);'
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[8], '
       '(ctrl->bRequestType << 8) | ctrl->bRequest);')
insert('irq_retry:\n\tgintsts = dwc2_readl(hsotg, GINTSTS);\n\tgintmsk = dwc2_readl(hsotg, GINTMSK);',
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[0], '
       'READ_ONCE(a6_usb_reconnect_trace[0]) + 1);'
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[4], gintsts);'
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[5], gintmsk);'
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[6], dwc2_readl(hsotg, DCTL));'
       '\n\tWRITE_ONCE(a6_usb_reconnect_trace[7], dwc2_readl(hsotg, DSTS));')
insert('u32 connected = hsotg->connected;',
       '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[1], '
       'READ_ONCE(a6_usb_reconnect_trace[1]) + 1);')
insert('if (gintsts & GINTSTS_ENUMDONE) {',
       '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[2], '
       'READ_ONCE(a6_usb_reconnect_trace[2]) + 1);')
if os.environ.get('A6_USB_RECONNECT_EP0') == '1':
    insert('if (gintsts & GINTSTS_RXFLVL) {',
           '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[9], '
           'READ_ONCE(a6_usb_reconnect_trace[9]) + 1);')
    insert('u32 grxstsr = dwc2_readl(hsotg, GRXSTSP);',
           '\n\tWRITE_ONCE(a6_usb_reconnect_trace[10], grxstsr);')
    insert('case GRXSTS_PKTSTS_SETUPRX:',
           '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[11], '
           'READ_ONCE(a6_usb_reconnect_trace[11]) + 1);')
    insert('u32 connected = hsotg->connected;',
           '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[12], usb_status);'
           '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[13], connected);')
    old = ('if (usb_status & GOTGCTL_BSESVLD && connected)\n'
           '\t\t\tdwc2_hsotg_core_init_disconnected(hsotg, true);')
    assert s.count(old) == 1, old
    s = s.replace(old,
        'if (usb_status & GOTGCTL_BSESVLD && connected) {\n'
        '\t\t\tWRITE_ONCE(a6_usb_reconnect_trace[14], '
        'READ_ONCE(a6_usb_reconnect_trace[14]) + 1);\n'
        '\t\t\tdwc2_hsotg_core_init_disconnected(hsotg, true);\n'
        '\t\t}')
    insert('struct dwc2_hsotg_req *hs_req = our_req(req);\n\tint ret;',
           '\n\tWRITE_ONCE(a6_usb_reconnect_trace[15], '
           'READ_ONCE(a6_usb_reconnect_trace[15]) + 1);')
    insert('if (!list_empty(&hs_req->queue)) {',
           '\n\t\tWRITE_ONCE(a6_usb_reconnect_trace[16], '
           'READ_ONCE(a6_usb_reconnect_trace[16]) + 1);')
    insert('/* ensure after enumeration our EP0 is active */\n\n\t'
           'dwc2_hsotg_enqueue_setup(hsotg);',
           '\n\tWRITE_ONCE(a6_usb_reconnect_trace[17], '
           'dwc2_readl(hsotg, DOEPCTL0));')
if os.environ.get('A6_USB_RECONNECT_REARM') == '1':
    old = 'if (usb_status & GOTGCTL_BSESVLD && connected)'
    assert s.count(old) == 1, old
    s = s.replace(old,
        'if ((usb_status & GOTGCTL_BSESVLD) && '
        '(connected || !(dwc2_readl(hsotg, DOEPCTL0) & '
        'DXEPCTL_EPENA)))')
if os.environ.get('A6_USB_RECONNECT_L3_REARM') == '1':
    assert os.environ.get('A6_USB_RECONNECT_REARM') != '1'
    old = 'if (usb_status & GOTGCTL_BSESVLD && connected)'
    assert s.count(old) == 1, old
    s = s.replace(old,
        'if ((usb_status & GOTGCTL_BSESVLD) && '
        '(connected || hsotg->lx_state == DWC2_L3))')
if os.environ.get('A6_USB_RECONNECT_ENUM_REARM') == '1':
    assert os.environ.get('A6_USB_RECONNECT_PHY') == '1'
    insert('u32 a6_usb_reconnect_trace[18];',
           '\nstatic bool a6_reconnect_had_address;'
           '\nstatic u32 a6_reconnect_reset_serial;'
           '\nstatic u32 a6_reconnect_rearmed_serial;'
           '\nstatic u32 a6_reconnect_rearm_total;')
    insert('case USB_REQ_SET_ADDRESS:',
           '\n\t\t\ta6_reconnect_had_address = true;'
           '\n\t\t\ta6_reconnect_rearmed_serial = '
           'a6_reconnect_reset_serial;')
    insert('if (gintsts & (GINTSTS_USBRST | GINTSTS_RESETDET)) {',
           '\n\t\ta6_reconnect_reset_serial++;')
    insert('dwc2_hsotg_irq_enumdone(hsotg);',
           '\n\t\t/* N42 guarded reconnect trial: once per reset, '
           'at most twice per boot. */'
           '\n\t\tif (a6_reconnect_had_address && '
           'a6_reconnect_rearm_total < 2 && '
           'a6_reconnect_rearmed_serial != a6_reconnect_reset_serial && '
           '(dwc2_readl(hsotg, GOTGCTL) & GOTGCTL_BSESVLD) && '
           '!(dwc2_readl(hsotg, DOEPCTL0) & DXEPCTL_EPENA)) {'
           '\n\t\t\ta6_reconnect_rearmed_serial = '
           'a6_reconnect_reset_serial;'
           '\n\t\t\ta6_reconnect_rearm_total++;'
           '\n\t\t\tdwc2_hsotg_core_init_disconnected(hsotg, true);'
           '\n\t\t}')
p.write_text(s)
TRACE
	fi
	cp "$repo_root/kernel/platform/phy-apple-a6-usb.c" "$linux_root/drivers/phy/phy-apple-a6-usb.c"
	printf '%s\n' 'obj-y += phy-apple-a6-usb.o' >> "$linux_root/drivers/phy/Makefile"
fi

if [[ "$legacy_control" != 1 ]]; then
	cp -- "$repo_root/kernel/platform/irq-apple-a6-aic.c" "$a6_irqchip"
	cp -- "$repo_root/kernel/platform/timer-apple-a6.c" "$a6_timer"
	printf '%s\n' 'obj-y += irq-apple-a6-aic.o' >>"$irqchip_makefile"
	if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
		printf '\nCFLAGS_irq-apple-a6-aic.o += -DA6_AIC_USB_FAIRNESS=1\n' >>"$irqchip_makefile"
        python3 - "$linux_root/drivers/video/fbdev/fb-apple-a6.c" "$repo_root/kernel/platform/a6-wifi-heartbeat.inc" <<'PY_WIFI_SCREEN'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
needle='static int __init a6_fb_init(void)'
assert s.count(needle)==1
s=s.replace(needle,Path(sys.argv[2]).read_text()+'\n'+needle)
needle='        pr_info("a6-drm: validated inherited framebuffer registered %ux%u\\n",'
assert s.count(needle)==1
s=s.replace(needle,'        error = device_create_file(&device->dev, &dev_attr_wifi_heartbeat);\n'
    '        if (error) {\n'
    '            platform_device_unregister(device);\n'
    '            return error;\n'
    '        }\n'+needle)
p.write_text(s)
PY_WIFI_SCREEN

	fi
	printf '%s\n' '' 'config APPLE_A6_AIC_IPI' '    bool' '    default y if SMP' '    select GENERIC_IRQ_IPI_MUX' >>"$irqchip_kconfig"
	printf '%s\n' 'obj-y += timer-apple-a6.o' >>"$clocksource_makefile"
fi

python3 - "$kernel_tlb_header" "$kernel_tlb_v7" "${A6_LOCAL_PAGE_TLBI:-0}" "${A6_LOCAL_ASID_TLBI:-0}" "${A6_LOCAL_RANGE_TLBI:-0}" "${A6_LOCAL_FULL_TLBI:-0}" <<'PY'
from pathlib import Path
import re
import sys

header = Path(sys.argv[1])
assembly = Path(sys.argv[2])
text = header.read_text()
old_smp = """#define v7wbi_tlb_flags_smp\t(TLB_WB | TLB_BARRIER | \\
\t\t\t\t TLB_V7_UIS_FULL | TLB_V7_UIS_PAGE | \\
\t\t\t\t TLB_V7_UIS_ASID | TLB_V7_UIS_BP)"""
old_up = """#define v7wbi_tlb_flags_up\t(TLB_WB | TLB_DCLEAN | TLB_BARRIER | \\
\t\t\t\t TLB_V6_U_FULL | TLB_V6_U_PAGE | \\
\t\t\t\t TLB_V6_U_ASID | TLB_V6_BP)"""
if text.count(old_smp) != 1 or text.count(old_up) != 1:
    raise SystemExit("could not locate ARMv7 TLB flag definitions")
text = text.replace(old_smp, "#define v7wbi_tlb_flags_smp\t(TLB_WB | TLB_BARRIER)")
page_flag = " | TLB_V6_U_PAGE" if sys.argv[3] == '1' else ""
asid_flag = " | TLB_V6_U_ASID" if sys.argv[4] == '1' else ""
full_flag = " | TLB_V6_U_FULL" if sys.argv[6] == "1" else ""
if full_flag and sys.argv[3:6] != ["1", "1", "1"]:
    raise SystemExit("full TLBI requires page, ASID and range TLBI")
text = text.replace(old_up, "#define v7wbi_tlb_flags_up\t(TLB_WB | TLB_BARRIER" + page_flag + asid_flag + full_flag + ")")
header.write_text(text)

# Keep stock range loops only in the explicit candidate: UP uses the
# already demonstrated c8,c7,1 operation. Full TLBI is independently gated.
if sys.argv[5] == "1":
    if sys.argv[3:5] != ["1", "1"]:
        raise SystemExit("range TLBI requires page and ASID TLBI")
    raise SystemExit(0)

text = assembly.read_text()
for name in ("v7wbi_flush_user_tlb_range", "v7wbi_flush_kern_tlb_range"):
    pattern = rf"(SYM_TYPED_FUNC_START\({name}\)\n).*?(SYM_FUNC_END\({name}\))"
    replacement = rf"\1\tdsb\tish\n\tisb\n\tret\tlr\n\2"
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"could not patch {name}")
assembly.write_text(text)
PY

if [[ "${A6_SMP_LOCAL_TLBI:-0}" == 1 ]]; then
    python3 "$repo_root/scripts/patch-a6-smp-local-tlbi.py" "$linux_root"
fi

if [[ "$legacy_control" != 1 ]]; then
if [[ "$legacy_control" != 1 ]]; then
python3 - "$compressed_head" "$usb_console" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()

# Keep decompressor execution/stack cached, but map the five 1 MiB sections
# containing the inflated Image non-cacheable. No dirty output lines then need
# Swift cache maintenance at handoff; only ordering barriers remain.
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
if sys.argv[2] == '1':
    # Integrated USB Image exceeds five MiB; bound it below eight MiB.
    replacement = replacement.replace('mov\tr2, #5', 'mov\tr2, #8')
text = text.replace(anchor, replacement, 1)

# The stock ARMv7 cache-off path also performs the full unified TLB invalidate
# that earlier A6 experiments found stops progress. Mirror the proven handoff:
# clear SCTLR.M/C, then synchronize, without issuing that unsafe operation.
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

# Swift's implementation ID is not represented in the generic decompressor
# processor table. Avoid dispatching these two final operations through a
# possibly mismatched MIDR entry: this port is A6-only and the handlers above
# are now explicitly the Swift-safe implementations.
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
\t\tb\tcall_cache_fn
"""
new = """cache_clean_flush:
\t\tmov\tr11, r1
\t\tb\t__armv7_mmu_cache_flush\t@ A6 Swift
"""
if text.count(old) != 1:
    raise SystemExit("could not locate decompressor cache-flush dispatcher")
text = text.replace(old, new, 1)

path.write_text(text)
PY
fi

python3 - "$compressed_head" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
needle = "\t\tbl\tdecompress_kernel\n\n\t\tget_inflated_image_size\tr1, r2, r3\n"
replacement = """\t\tbl\tdecompress_kernel

\t\t/* A6 port breadcrumb: blue means decompression completed and the
\t\t * generic ARMv7 cache clean has not yet returned. */
\t\tldr\tr0, =0x83fff000
\t\tldr\tr1, [r0]
\t\tldr\tr2, [r0, #4]
\t\tcmp\tr1, #0
\t\tbeq\t9f
\t\tcmp\tr2, #0
\t\tbeq\t9f
\t\tldr\tr3, =0x000000ff
8:\t\tstr\tr3, [r1], #4
\t\tsubs\tr2, r2, #1
\t\tbne\t8b
9:\t\tdsb\tsy

\t\tget_inflated_image_size\tr1, r2, r3
"""
if text.count(needle) != 1:
    raise SystemExit("could not locate unique decompressor return site")
path.write_text(text.replace(needle, replacement))
PY

python3 - "$compressed_head" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

def paint(colour, comment):
    return f"""\t\t/* A6 port breadcrumb: {comment}. */
\t\tldr\tr0, =0x83fff000
\t\tldr\tr1, [r0]
\t\tldr\tr2, [r0, #4]
\t\tcmp\tr1, #0
\t\tbeq\t9f
\t\tcmp\tr2, #0
\t\tbeq\t9f
\t\tldr\tr3, ={colour}
8:\t\tstr\tr3, [r1], #4
\t\tsubs\tr2, r2, #1
\t\tbne\t8b
9:\t\tdsb\tsy
"""

old = "\t\tbl\tcache_clean_flush\n\t\tbl\tcache_off\n"
new = ("\t\tbl\tcache_clean_flush\n" +
       paint("0x00ffff00", "yellow means the generic cache clean returned") +
       "\t\tbl\tcache_off\n" +
       paint("0x0000ffff", "cyan means cache-off returned; entering Linux") )
if text.count(old) != 1:
    raise SystemExit("could not locate unique final cache transition")
path.write_text(text.replace(old, new, 1))
PY
fi

python3 - "$kernel_head" "$repo_root/kernel/font8x8.bin" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
font = Path(sys.argv[2]).resolve()
text = path.read_text()
needle = "ENTRY(stext)\n ARM_BE8(setend\tbe )"
replacement = """.macro a6_paint low, high
\tpush\t{r0, r3-r6, r12, lr}
\tmovw\tr3, #0xf000
\tmovt\tr3, #0x83ff
\tldr\tr4, [r3]
\tldr\tr5, [r3, #4]
\tcmp\tr4, #0
\tbeq\t991f
\tcmp\tr5, #0
\tbeq\t991f
\tmovw\tr6, #\\low
\tmovt\tr6, #\\high
990:\tstr\tr6, [r4], #4
\tsubs\tr5, r5, #1
\tbne\t990b
\tdsb\tsy
991:\tpop\t{r0, r3-r6, r12, lr}
.endm

.macro a6_text label
\tpush\t{r0-r12, lr}
\tadr\tr0, \\label
\tbl\ta6_draw_text
\tpop\t{r0-r12, lr}
.endm

ENTRY(stext)
\t/* Magenta: uncompressed kernel entry. */
\ta6_paint 0x00ff, 0x00ff
 ARM_BE8(setend\tbe )"""
if text.count(needle) != 1:
    raise SystemExit("could not locate unique ARM kernel entry")
text = text.replace(needle, replacement)
text = text.replace("\tsafe_svcmode_maskall r9\n", "\tsafe_svcmode_maskall r9\n\ta6_text a6_msg_entry\n", 1)
checkpoints = [
    ("\tbeq\t__error_p\t\t\t@ yes, error 'p'\n",
     "\tbeq\t__error_p\t\t\t@ yes, error 'p'\n\ta6_paint 0xffff, 0x0000\t\t@ cyan: processor matched\n\ta6_text a6_msg_cpu\n"),
    ("\tbl\t__vet_atags\n", "\tbl\t__vet_atags\n\ta6_paint 0xff00, 0x00ff\t\t@ yellow: DT vetted\n\ta6_text a6_msg_dtb\n"),
    ("\tbl\t__create_page_tables\n", "\tbl\t__create_page_tables\n\ta6_paint 0xffff, 0xffff\t\t@ white: page tables built\n\ta6_text a6_msg_pages\n"),
    ("\tldr\tr13, =__mmap_switched\t\t@ address to jump to after\n",
     "\ta6_paint 0x8000, 0x00ff\t\t@ orange: entering CPU/MMU setup\n"
     "\ta6_text a6_msg_mmu\n"
     "\tldr\tr13, =__mmap_switched\t\t@ address to jump to after\n"),
]
for old, new in checkpoints:
    if text.count(old) < 1:
        raise SystemExit(f"could not locate checkpoint: {old!r}")
    text = text.replace(old, new, 1)
setup_return = "\tret\tr12\n1:\tb\t__enable_mmu\n"
if text.count(setup_return) != 1:
    raise SystemExit("could not locate primary CPU setup return")
text = text.replace(
    setup_return,
    "\tret\tr12\n1:\t/* Stackless: r13 now holds __mmap_switched. */\n"
    "\tmovw\tr3, #0xf000\n"
    "\tmovt\tr3, #0x83ff\n"
    "\tldr\tr6, [r3]\n"
    "\tldr\tr7, [r3, #4]\n"
    "\tmovw\tr10, #0x07e0\n"
    "19:\tstr\tr10, [r6], #4\n"
    "\tsubs\tr7, r7, #1\n"
    "\tbne\t19b\n"
    "\tdsb\tsy\n"
    "\tb\t__enable_mmu\n",
    1,
)
map_anchor = "\tstrne\tr6, [r3]\n\n#if defined(CONFIG_ARM_LPAE)"
map_code = """\tstrne\tr6, [r3]

	/* Keep the A6 diagnostic scratch page identity-mapped after MMU-on. */
	ldr	r0, =0x83f00000
	mov	r5, r0, lsr #SECTION_SHIFT
	orr	r3, r7, r0
	str	r3, [r4, r5, lsl #PMD_ENTRY_ORDER]

	/* Identity-map eight MiB around the live iBEC framebuffer. */
	ldr	r0, =0xbf7aa000
	mov	r5, r0, lsr #SECTION_SHIFT
	mov	r0, r5, lsl #SECTION_SHIFT
	mov	r6, #8
	ldr	r7, [r10, #PROCINFO_IO_MMUFLAGS]
98:	orr	r3, r7, r0
	orr	r3, r3, #PMD_SECT_XN
	str	r3, [r4, r5, lsl #PMD_ENTRY_ORDER]
	add	r0, r0, #1 << SECTION_SHIFT
	add	r5, r5, #1
	subs	r6, r6, #1
	bne	98b
	ldr	r7, [r10, #PROCINFO_MM_MMUFLAGS]

#if defined(CONFIG_ARM_LPAE)"""
if text.count(map_anchor) != 1:
    raise SystemExit("could not locate initial page-table mapping anchor")
text = text.replace(map_anchor, map_code, 1)
tail = "ENDPROC(stext)\n\t.ltorg"
font_path = str(font).replace('\\\\', '/')
support = f'''ENDPROC(stext)
	.ltorg

/* Tiny pre-MMU framebuffer text renderer, 3x scaled 8x8 glyphs. */
.pushsection .data
\t.align 2
.global a6_fb_base_saved, a6_fb_words_saved, a6_fb_stride_saved
a6_fb_base_saved:  .word 0xbf7aa000
a6_fb_words_saved: .word 0x000b1800
a6_fb_stride_saved:.word 0x000011c0
.popsection

a6_draw_text:
\t/* Valid in both the physical pre-MMU and virtual post-MMU phases. */
\tmovw\tr1, #0xf000
\tmovt\tr1, #0x83ff
\tldr\tr4, [r1]
\tldr\tr5, [r1, #8]
\tadd\tr4, r4, r5, lsl #5
\tadd\tr4, r4, #48
\tmov\tr6, #0
\tadr.w\tr10, a6_font
10:\tldrb\tr7, [r0], #1
\tcmp\tr7, #0
\tbxeq\tlr
\tadd\tr9, r10, r7, lsl #3
\tmov\tr8, #0
11:\tldrb\tr11, [r9, r8]
\tadd\tr1, r4, r6, lsl #2
\tmul\tr2, r8, r5
\tadd\tr1, r1, r2, lsl #1
\tadd\tr1, r1, r2
\tadd\tr2, r1, r5
\tadd\tr3, r2, r5
\tmov\tr12, #0
\tmov\tr7, #0
12:\ttst\tr11, #0x80
\tbeq\t13f
\tstr\tr12, [r1], #4
\tstr\tr12, [r1], #4
\tstr\tr12, [r1], #4
\tstr\tr12, [r2], #4
\tstr\tr12, [r2], #4
\tstr\tr12, [r2], #4
\tstr\tr12, [r3], #4
\tstr\tr12, [r3], #4
\tstr\tr12, [r3], #4
\tb\t14f
13:\tadd\tr1, r1, #12
\tadd\tr2, r2, #12
\tadd\tr3, r3, #12
14:
\tlsl\tr11, r11, #1
\tadd\tr7, r7, #1
\tcmp\tr7, #8
\tblo\t12b
\tadd\tr8, r8, #1
\tcmp\tr8, #8
\tblo\t11b
\tadd\tr6, r6, #27
\tb\t10b

/* Post-MMU markers called from head-common.S with identity-mapped video. */
.global a6_post_mmu_marker
.global a6_post_bss_marker
.global a6_post_start_marker
.type a6_post_mmu_marker, %function
.type a6_post_bss_marker, %function
.type a6_post_start_marker, %function
a6_post_mmu_marker:
\tpush\t{{r0-r12, lr}}
\tmovw\tr2, #0xf000
\tmovt\tr2, #0x83ff
\tmovw\tr3, #:lower16:a6_fb_base_saved
\tmovt\tr3, #:upper16:a6_fb_base_saved
\tldr\tr4, [r2]
\tstr\tr4, [r3]
\tldr\tr4, [r2, #4]
\tstr\tr4, [r3, #4]
\tldr\tr4, [r2, #8]
\tstr\tr4, [r3, #8]
\tpop\t{{r0-r12, pc}}
a6_post_bss_marker:
\tbx\tlr
a6_post_start_marker:
\tbx\tlr
a6_post_marker:
\tpush\t{{r1, lr}}
\tmovw\tr2, #:lower16:a6_fb_base_saved
\tmovt\tr2, #:upper16:a6_fb_base_saved
\tldr\tr4, [r2]
\tldr\tr5, [r2, #4]
15:\tstr\tr0, [r4], #4
\tsubs\tr5, r5, #1
\tbne\t15b
\tdsb\tsy
\tldr\tr0, [sp]
\tbl\ta6_draw_text
\t/* Keep each checkpoint visible long enough to read on the LCD. */
\tmov\tr6, #1
\tldr\tr7, =0x00200000
17:\tmov\tr8, r7
18:\tsubs\tr8, r8, #1
\tbne\t18b
\tsubs\tr6, r6, #1
\tbne\t17b
16:\tpop\t{{r1, pc}}

.macro a6_c_stage name, low, high, message
.global \\name
.type \\name, %function
\\name:
\tbx\tlr
.endm

.macro a6_visible_stage name, low, high, message
.global \\name
.type \\name, %function
\\name:
\tpush\t{{r0-r12, lr}}
\tmrs\tr2, cpsr
\tpush\t{{r2, r3}}
\tmovw\tr0, #\\low
\tmovt\tr0, #\\high
\tadr\tr1, \\message
\tbl\ta6_post_marker
\tpop\t{{r2, r3}}
\tmsr\tcpsr_f, r2
\tpop\t{{r0-r12, pc}}
.endm

/* Low-overhead trace: paint a visible 48-line band near screen center. */
.macro a6_quick_stage name, low, high
.global \\name
.type \\name, %function
\\name:
\tpush\t{{r0-r5, lr}}
\tmovw\tr0, #:lower16:a6_fb_base_saved
\tmovt\tr0, #:upper16:a6_fb_base_saved
\tldr\tr1, [r0]
\tldr\tr2, [r0, #8]
\tmov\tr3, #160
\tmul\tr5, r3, r2
\tadd\tr1, r1, r5
\tmov\tr3, #48
\tmul\tr2, r3, r2
\tlsr\tr2, r2, #2
\tmovw\tr4, #\\low
\tmovt\tr4, #\\high
991:\tstr\tr4, [r1], #4
\tsubs\tr2, r2, #1
\tbne\t991b
\tdsb\tsy
\tpop\t{{r0-r5, pc}}
.endm

a6_c_stage a6_stage_stack,  0x001f, 0x0000, a6_msg_stack
a6_c_stage a6_stage_cpuid,  0xffff, 0x0000, a6_msg_cpuid
a6_c_stage a6_stage_build,  0xffe0, 0x0000, a6_msg_build
a6_c_stage a6_stage_cgroup, 0xffff, 0xffff, a6_msg_cgroup
a6_c_stage a6_stage_irqoff, 0x07ff, 0x0000, a6_msg_irqoff
a6_c_stage a6_stage_bootcpu,0x001f, 0x07e0, a6_msg_bootcpu
a6_c_stage a6_stage_page,   0xffe0, 0x07e0, a6_msg_page
a6_c_stage a6_stage_banner, 0xf81f, 0x07e0, a6_msg_banner
a6_c_stage a6_stage_archin, 0xffff, 0x07e0, a6_msg_archin
a6_c_stage a6_stage_arch,   0xf81f, 0x0000, a6_msg_arch
a6_c_stage a6_stage_mmearly,0x001f, 0x03ff, a6_msg_mmearly
a6_c_stage a6_stage_percpu, 0x07ff, 0x03ff, a6_msg_percpu
a6_c_stage a6_stage_args,   0xffe0, 0x03ff, a6_msg_args
a6_c_stage a6_stage_mmcore, 0xf81f, 0x03ff, a6_msg_mmcore
a6_c_stage a6_stage_sched,  0xffff, 0x03ff, a6_msg_sched
a6_c_stage a6_stage_irq,    0x001f, 0x0010, a6_msg_irq
a6_c_stage a6_stage_time,   0x07ff, 0x0010, a6_msg_time
a6_c_stage a6_stage_irqon,  0xffe0, 0x0010, a6_msg_irqon
a6_c_stage a6_stage_console,0xf81f, 0x0010, a6_msg_console
a6_c_stage a6_stage_locking,0x001f, 0x4210, a6_msg_locking
a6_c_stage a6_stage_pageset,0x07ff, 0x4210, a6_msg_pageset
a6_c_stage a6_stage_delay,  0xffe0, 0x4210, a6_msg_delay
a6_c_stage a6_stage_archfinal,0xf81f,0x4210,a6_msg_archfinal
a6_c_stage a6_stage_fork,   0xffff, 0x4210, a6_msg_fork
a6_c_stage a6_stage_vfs,    0x001f, 0x0210, a6_msg_vfs
a6_c_stage a6_stage_cgroups,0x07ff, 0x0210, a6_msg_cgroups
a6_c_stage a6_stage_rest,   0xffff, 0x0010, a6_msg_rest
a6_c_stage a6_rest_pid1,    0x001f, 0x6318, a6_msg_rest_pid1
a6_c_stage a6_rest_kthread, 0x07ff, 0x6318, a6_msg_rest_kthread
a6_quick_stage a6_kinit_enter,0x001f,0x0000
a6_c_stage a6_kinit_basic,  0xf81f, 0x6318, a6_msg_kinit_basic
a6_c_stage a6_kinit_ramfs,  0xffff, 0x6318, a6_msg_kinit_ramfs
a6_quick_stage a6_kinit_ready,0x07e0,0x0000
a6_quick_stage a6_kinit_exec,0x001f,0x001f
a6_c_stage a6_kinit_fail,   0xf800, 0x0000, a6_msg_kinit_fail
a6_visible_stage a6_userspace_syscall, 0x07e0, 0xffff, a6_msg_userspace_syscall
a6_visible_stage a6_counter_proof, 0x07e0, 0x0000, a6_msg_counter_proof
a6_visible_stage a6_timer_irq_proof, 0xffff, 0x0000, a6_msg_timer_irq_proof
a6_quick_stage a6_user_return,0x8000,0x00ff
a6_quick_stage a6_user_svc,   0x07ff,0xffff
a6_c_stage a6_exec_bprm,   0x001f, 0x7bef, a6_msg_exec_bprm
a6_quick_stage a6_exec_handler,0xf81f,0x0000
a6_quick_stage a6_elf_enter,0xffff,0x0000
a6_c_stage a6_elf_headers, 0xf81f, 0x7bef, a6_msg_elf_headers
a6_c_stage a6_exec_begin,  0xffff, 0x7bef, a6_msg_exec_begin
a6_c_stage a6_exec_mmap_pre,0x001f,0x4210,a6_msg_exec_mmap_pre
a6_quick_stage a6_exec_mmap_ok,0x001f,0x0000
a6_quick_stage a6_exec_ns_ok,  0x07e0,0x0000
a6_quick_stage a6_exec_sig_ok, 0x001f,0x001f
a6_quick_stage a6_exec_thr_ok, 0xf81f,0x0000
a6_quick_stage a6_exec_perf_ok,0xffff,0x0000
a6_quick_stage a6_exec_cred_ok,0xffe0,0x07ff
a6_quick_stage a6_exec_done,   0xffff,0xffff
a6_quick_stage a6_elf_stack,  0x07ff,0x0000
a6_quick_stage a6_elf_mapped, 0xf800,0x001f
a6_quick_stage a6_elf_tables, 0xffff,0x03ff
a6_quick_stage a6_elf_regs,   0x07ff,0x07e0
a6_c_stage a6_arch_proc,    0x001f, 0xf800, a6_msg_arch_proc
a6_c_stage a6_arch_fdt,     0x07ff, 0xf800, a6_msg_arch_fdt
a6_c_stage a6_arch_initmm,  0xffe0, 0xf800, a6_msg_arch_initmm
a6_c_stage a6_arch_fixmap,  0xffff, 0xf800, a6_msg_arch_fixmap
a6_c_stage a6_arch_memblock,0xf81f, 0xf800, a6_msg_arch_memblock
a6_c_stage a6_arch_pagingin,0xffff, 0xffff, a6_msg_arch_pagingin
a6_c_stage a6_arch_paging,  0x07e0, 0x0000, a6_msg_arch_paging
a6_c_stage a6_page_prepare, 0x001f, 0xffff, a6_msg_page_prepare
a6_c_stage a6_page_lowmem,  0x07ff, 0xffff, a6_msg_page_lowmem
a6_c_stage a6_page_kernel,  0xffe0, 0xffff, a6_msg_page_kernel
a6_c_stage a6_page_dma,     0x001f, 0x07ff, a6_msg_page_dma
a6_c_stage a6_page_fixdown, 0x07ff, 0x07ff, a6_msg_page_fixdown
a6_c_stage a6_page_devin,   0xffe0, 0x07ff, a6_msg_page_devin
a6_c_stage a6_page_vectors, 0xf81f, 0x07ff, a6_msg_page_vectors
a6_c_stage a6_page_traps,   0xffff, 0x07ff, a6_msg_page_traps
a6_c_stage a6_dev_clear,    0x001f, 0xf81f, a6_msg_dev_clear
a6_c_stage a6_dev_dtb,      0x07ff, 0xf81f, a6_msg_dev_dtb
a6_c_stage a6_dev_vectors,  0xffe0, 0xf81f, a6_msg_dev_vectors
a6_c_stage a6_dev_debug,    0xf81f, 0xf81f, a6_msg_dev_debug
a6_c_stage a6_dev_pci,      0xffff, 0xf81f, a6_msg_dev_pci
a6_c_stage a6_tlb_enter,    0x001f, 0x7bef, a6_msg_tlb_enter
a6_c_stage a6_tlb_pre,      0x07ff, 0x7bef, a6_msg_tlb_pre
a6_c_stage a6_tlb_dinv,     0xffe0, 0x7bef, a6_msg_tlb_dinv
a6_c_stage a6_tlb_iinv,     0x07e0, 0x7bef, a6_msg_tlb_iinv
a6_c_stage a6_tlb_post,     0xf81f, 0x7bef, a6_msg_tlb_post
a6_c_stage a6_tlb_isb,      0xffff, 0x7bef, a6_msg_tlb_isb
a6_c_stage a6_dev_tlb,      0x001f, 0x001f, a6_msg_dev_tlb
a6_c_stage a6_dev_cache,    0x07ff, 0x001f, a6_msg_dev_cache
a6_c_stage a6_dev_abort,    0xffe0, 0x001f, a6_msg_dev_abort
a6_c_stage a6_page_devices, 0xf81f, 0xffff, a6_msg_page_devices
a6_c_stage a6_page_bootmem, 0x07e0, 0xffff, a6_msg_page_bootmem

a6_c_stage a6_check_magic, 0x07ff, 0x001f, a6_msg_check_magic
a6_c_stage a6_check_arch, 0x07ff, 0x001f, a6_msg_check_arch
a6_c_stage a6_check_phalloc, 0x07ff, 0x001f, a6_msg_check_phalloc
a6_c_stage a6_check_phread, 0x07ff, 0x001f, a6_msg_check_phread
a6_c_stage a6_check_phdone, 0x07ff, 0x001f, a6_msg_check_phdone
a6_c_stage a6_check_reject, 0x07ff, 0x001f, a6_msg_check_reject

a6_msg_check_magic: .asciz "ELF MAGIC OK"
a6_msg_check_arch: .asciz "ELF ARCH OK"
a6_msg_check_phalloc: .asciz "PHDR ALLOC ENTER"
a6_msg_check_phread: .asciz "PHDR READ ENTER"
a6_msg_check_phdone: .asciz "PHDR READ RETURN"
a6_msg_check_reject: .asciz "ELF REJECTED"

a6_c_stage a6_mm_state, 0x07ff, 0x07e0, a6_msg_mm_state
a6_c_stage a6_mm_lock, 0x07ff, 0x07e0, a6_msg_mm_lock
a6_c_stage a6_mm_activate, 0x07ff, 0x07e0, a6_msg_mm_activate
a6_c_stage a6_mm_vmalloc, 0x07ff, 0x07e0, a6_msg_mm_vmalloc
a6_c_stage a6_mm_reserved, 0x07ff, 0x07e0, a6_msg_mm_reserved
a6_c_stage a6_mm_asid, 0x07ff, 0x07e0, a6_msg_mm_asid
a6_c_stage a6_mm_switched, 0x07ff, 0x07e0, a6_msg_mm_switched
a6_visible_stage a6_fault_undef, 0xf81f, 0x001f, a6_msg_fault_undef
a6_visible_stage a6_fault_memory,0xffff, 0x001f, a6_msg_fault_memory
a6_msg_mm_state: .asciz "EXEC STATE OK"
a6_msg_mm_lock: .asciz "EXEC LOCK OK"
a6_msg_mm_activate: .asciz "ACTIVATE MM"
a6_msg_mm_vmalloc: .asciz "VMALLOC SYNC OK"
a6_msg_mm_reserved: .asciz "RESERVED TTBR OK"
a6_msg_mm_asid: .asciz "ASID READY"
a6_msg_mm_switched: .asciz "CPU MM SWITCH OK"
a6_msg_fault_undef: .asciz "FAULT UNDEFINED INSTR"
a6_msg_fault_memory:.asciz "FAULT MEMORY ACCESS"

a6_msg_entry: .asciz "LINUX ENTRY"
a6_msg_cpu:   .asciz "CPU MATCHED"
a6_msg_dtb:   .asciz "DTB VALID"
a6_msg_pages: .asciz "PAGES BUILT"
a6_msg_mmu:   .asciz "ENTER MMU"
a6_msg_setup: .asciz "CPU SETUP OK"
a6_msg_mmu_on:.asciz "MMU ON"
a6_msg_bss:   .asciz "BSS OK"
a6_msg_start: .asciz "START KERNEL"
a6_msg_stack: .asciz "STACK GUARD OK"
a6_msg_cpuid: .asciz "CPU ID OK"
a6_msg_build: .asciz "BUILD ID OK"
a6_msg_cgroup:.asciz "CGROUP EARLY OK"
a6_msg_irqoff:.asciz "IRQS OFF"
a6_msg_bootcpu:.asciz "BOOT CPU OK"
a6_msg_page:  .asciz "PAGE ADDRESS OK"
a6_msg_banner:.asciz "BANNER OK"
a6_msg_archin:.asciz "ENTER SETUP ARCH"
a6_msg_arch:  .asciz "SETUP ARCH OK"
a6_msg_mmearly:.asciz "MM CORE EARLY OK"
a6_msg_percpu:.asciz "PERCPU OK"
a6_msg_args:.asciz "BOOT ARGS OK"
a6_msg_mmcore:.asciz "MM CORE OK"
a6_msg_sched:.asciz "SCHEDULER OK"
a6_msg_irq:.asciz "IRQ INIT OK"
a6_msg_time:.asciz "TIME INIT OK"
a6_msg_irqon:.asciz "IRQS ENABLED"
a6_msg_console:.asciz "CONSOLE INIT OK"
a6_msg_locking:.asciz "LOCKING INIT OK"
a6_msg_pageset:.asciz "PERCPU PAGESET OK"
a6_msg_delay:.asciz "DELAY CALIBRATION OK"
a6_msg_archfinal:.asciz "ARCH FINALIZE OK"
a6_msg_fork:.asciz "FORK INIT OK"
a6_msg_vfs:.asciz "VFS INIT OK"
a6_msg_cgroups:.asciz "CGROUP INIT OK"
a6_msg_rest:.asciz "ENTER REST INIT"
a6_msg_rest_pid1:.asciz "PID 1 CREATED"
a6_msg_rest_kthread:.asciz "KTHREADD CREATED"
a6_msg_kinit_enter:.asciz "KERNEL INIT THREAD"
a6_msg_kinit_basic:.asciz "KERNEL INITCALLS OK"
a6_msg_kinit_ramfs:.asciz "INITRAMFS READY"
a6_msg_kinit_ready:.asciz "KERNEL INIT READY"
a6_msg_kinit_exec:.asciz "EXEC /INIT"
a6_msg_kinit_fail:.asciz "INIT EXEC FAILED"
a6_msg_userspace_syscall:.asciz "USERSPACE SYSCALL OK"
a6_msg_counter_proof:.asciz "A6 COUNTER ADVANCES"
a6_msg_timer_irq_proof:.asciz "A6 TIMER IRQ REPEATS"
a6_msg_user_return:.asciz "ENTER USER MODE"
a6_msg_user_svc:   .asciz "USER SVC ENTRY"
a6_msg_exec_bprm:  .asciz "EXEC BPRM READY"
a6_msg_exec_handler:.asciz "EXEC HANDLER"
a6_msg_elf_enter:  .asciz "ELF LOADER ENTER"
a6_msg_elf_headers:.asciz "ELF HEADERS OK"
a6_msg_exec_begin: .asciz "BEGIN NEW EXEC"
a6_msg_exec_mmap_pre:.asciz "EXEC MMAP ENTER"
a6_msg_exec_mmap_ok:.asciz "EXEC MMAP OK"
a6_msg_elf_stack:  .asciz "ELF STACK OK"
a6_msg_elf_mapped: .asciz "ELF SEGMENTS OK"
a6_msg_elf_tables: .asciz "ELF TABLES OK"
a6_msg_elf_regs:   .asciz "ELF REGS READY"
a6_msg_arch_proc:.asciz "PROCESSOR OK"
a6_msg_arch_fdt:.asciz "MACHINE FDT OK"
a6_msg_arch_initmm:.asciz "INITIAL MM OK"
a6_msg_arch_fixmap:.asciz "FIXMAP OK"
a6_msg_arch_memblock:.asciz "MEMBLOCK OK"
a6_msg_arch_pagingin:.asciz "ENTER PAGING"
a6_msg_arch_paging:.asciz "PAGING OK"
a6_msg_page_prepare:.asciz "PAGE TABLE PREP OK"
a6_msg_page_lowmem:.asciz "LOWMEM MAP OK"
a6_msg_page_kernel:.asciz "KERNEL MAP OK"
a6_msg_page_dma:.asciz "DMA REMAP OK"
a6_msg_page_fixdown:.asciz "FIXMAP SHUTDOWN OK"
a6_msg_page_devin:.asciz "ENTER DEVICE MAPS"
a6_msg_page_vectors:.asciz "VECTOR ALLOC OK"
a6_msg_page_traps:.asciz "TRAP INIT OK"
a6_msg_dev_clear:.asciz "VMALLOC CLEAR OK"
a6_msg_dev_dtb:.asciz "DT REMAP OK"
a6_msg_dev_vectors:.asciz "VECTOR MAPS OK"
a6_msg_dev_debug:.asciz "DEBUG MAPS OK"
a6_msg_dev_pci:.asciz "PCI RESERVE OK"
a6_msg_tlb_enter:.asciz "ENTER TLB FLUSH"
a6_msg_tlb_pre:.asciz "TLB PRE BARRIER OK"
a6_msg_tlb_dinv:.asciz "DATA TLB INVALIDATE OK"
a6_msg_tlb_iinv:.asciz "INST TLB INVALIDATE OK"
a6_msg_tlb_post:.asciz "TLB POST BARRIER OK"
a6_msg_tlb_isb:.asciz "TLB ISB OK"
a6_msg_dev_tlb:.asciz "TLB FLUSH OK"
a6_msg_dev_cache:.asciz "CACHE FLUSH OK"
a6_msg_dev_abort:.asciz "ABORTS ENABLED"
a6_msg_page_devices:.asciz "DEVICE MAPS OK"
a6_msg_page_bootmem:.asciz "BOOTMEM OK"
\t.align 2
a6_font:
\t.incbin "{font_path}"
\t.ltorg'''
if text.count(tail) != 1:
    raise SystemExit("could not locate primary stext tail")
text = text.replace(tail, support, 1)
path.write_text(text)
PY

python3 - "$kernel_setup" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
entry = "void __init setup_arch(char **cmdline_p)\n"
decls = """extern void a6_arch_proc(void);
extern void a6_arch_fdt(void);
extern void a6_arch_initmm(void);
extern void a6_arch_fixmap(void);
extern void a6_arch_memblock(void);
extern void a6_arch_pagingin(void);
extern void a6_arch_paging(void);

void __init setup_arch(char **cmdline_p)
"""
if text.count(entry) != 1:
    raise SystemExit("could not locate setup_arch declaration")
text = text.replace(entry, decls, 1)
replacements = [
    ("\tsetup_processor();\n", "\tsetup_processor();\n\ta6_arch_proc();\n"),
    ("\tmachine_desc = mdesc;\n", "\ta6_arch_fdt();\n\tmachine_desc = mdesc;\n"),
    ("\tsetup_initial_init_mm(_text, _etext, _edata, _end);\n", "\tsetup_initial_init_mm(_text, _etext, _edata, _end);\n\ta6_arch_initmm();\n"),
    ("\tearly_ioremap_init();\n", "\tearly_ioremap_init();\n\ta6_arch_fixmap();\n"),
    ("\tarm_memblock_init(mdesc);\n", "\tarm_memblock_init(mdesc);\n\ta6_arch_memblock();\n"),
    ("\tpaging_init(mdesc);\n", "\ta6_arch_pagingin();\n\tpaging_init(mdesc);\n\ta6_arch_paging();\n"),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate setup_arch checkpoint: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
PY

python3 - "$kernel_mmu" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

# Keep the temporary A6 framebuffer/scratch identity window alive while
# paging_init replaces the boot page tables. This is diagnostics-only and is
# intentionally removed once the port has a working serial console.
old = "\tfor (addr = 0; addr < MODULES_VADDR; addr += PMD_SIZE)\n\t\tpmd_clear(pmd_off_k(addr));\n"
new = """\tfor (addr = 0; addr < MODULES_VADDR; addr += PMD_SIZE) {
\t\tif (addr >= 0x83000000UL && addr < 0x85000000UL)
\t\t\tcontinue;
\t\tpmd_clear(pmd_off_k(addr));
\t}
"""
if text.count(old) != 1:
    raise SystemExit("could not locate non-KASAN low mapping clear loop")
text = text.replace(old, new, 1)

# The live iBEC framebuffer occupies 0xbf7aa000 onward. It sits in the ARM
# module-area virtual range, so prepare_page_table() would normally clear its
# early identity mapping. Preserve that diagnostic mapping until a native
# framebuffer driver replaces it.
old = "\tfor ( ; addr < PAGE_OFFSET; addr += PMD_SIZE)\n\t\tpmd_clear(pmd_off_k(addr));\n"
new = """\tfor ( ; addr < PAGE_OFFSET; addr += PMD_SIZE) {
\t\tif (addr >= 0xbf000000UL)
\t\t\tcontinue;
\t\tpmd_clear(pmd_off_k(addr));
\t}
"""
if text.count(old) != 1:
    raise SystemExit("could not locate module-area mapping clear loop")
text = text.replace(old, new, 1)

dev_entry = "static void __init devicemaps_init(const struct machine_desc *mdesc)\n"
dev_decls = """extern void a6_page_vectors(void);
extern void a6_page_traps(void);
extern void a6_dev_clear(void);
extern void a6_dev_dtb(void);
extern void a6_dev_vectors(void);
extern void a6_dev_debug(void);
extern void a6_dev_pci(void);
extern void a6_tlb_enter(void);
extern void a6_tlb_pre(void);
extern void a6_tlb_dinv(void);
extern void a6_tlb_iinv(void);
extern void a6_tlb_post(void);
extern void a6_tlb_isb(void);
extern void a6_dev_tlb(void);
extern void a6_dev_cache(void);
extern void a6_dev_abort(void);

static void __init devicemaps_init(const struct machine_desc *mdesc)
"""
if text.count(dev_entry) != 1:
    raise SystemExit("could not locate devicemaps_init declaration")
text = text.replace(dev_entry, dev_decls, 1)

entry = "void __init paging_init(const struct machine_desc *mdesc)\n"
decls = """extern void a6_page_prepare(void);
extern void a6_page_lowmem(void);
extern void a6_page_kernel(void);
extern void a6_page_dma(void);
extern void a6_page_fixdown(void);
extern void a6_page_devin(void);
extern void a6_page_vectors(void);
extern void a6_page_traps(void);
extern void a6_page_devices(void);
extern void a6_page_bootmem(void);

void __init paging_init(const struct machine_desc *mdesc)
"""
if text.count(entry) != 1:
    raise SystemExit("could not locate paging_init declaration")
text = text.replace(entry, decls, 1)
checks = [
    ("\t\tpmd_clear(pmd_off_k(addr));\n\n\tif (__atags_pointer)", "\t\tpmd_clear(pmd_off_k(addr));\n\ta6_dev_clear();\n\n\tif (__atags_pointer)"),
    ("\t}\n\n\t/*\n\t * Map the cache flushing regions.", "\t}\n\ta6_dev_dtb();\n\n\t/*\n\t * Map the cache flushing regions."),
    ("\tcreate_mapping(&map);\n\n\t/*\n\t * Ask the machine support", "\tcreate_mapping(&map);\n\ta6_dev_vectors();\n\n\t/*\n\t * Ask the machine support"),
    ("\tfill_pmd_gaps();\n", "\tfill_pmd_gaps();\n\ta6_dev_debug();\n"),
    ("\tpci_reserve_io();\n", "\tpci_reserve_io();\n\ta6_dev_pci();\n"),
    ("\tlocal_flush_tlb_all();\n\tflush_cache_all();\n", """\t/* Apple Swift hangs on ARMv7 CP15 c8 TLB invalidation. The
\t * replacement tables and diagnostic mappings are already active; carry
\t * stale entries temporarily to reach later platform initialization. */
\ta6_dev_tlb();
\tflush_cache_all();
\ta6_dev_cache();
"""),
    ("\tearly_abt_enable();\n", "\tearly_abt_enable();\n\ta6_dev_abort();\n"),
    ("\tvectors = early_alloc(PAGE_SIZE * 2);\n", "\tvectors = early_alloc(PAGE_SIZE * 2);\n\ta6_page_vectors();\n"),
    ("\tearly_trap_init(vectors);\n", "\tearly_trap_init(vectors);\n\ta6_page_traps();\n"),
    ("\tprepare_page_table();\n", "\tprepare_page_table();\n\ta6_page_prepare();\n"),
    ("\tmap_lowmem();\n", "\tmap_lowmem();\n\ta6_page_lowmem();\n"),
    ("\tmap_kernel();\n", "\tmap_kernel();\n\ta6_page_kernel();\n"),
    ("\tdma_contiguous_remap();\n", "\tdma_contiguous_remap();\n\ta6_page_dma();\n"),
    ("\tearly_fixmap_shutdown();\n", "\tearly_fixmap_shutdown();\n\ta6_page_fixdown();\n\ta6_page_devin();\n"),
    ("\tdevicemaps_init(mdesc);\n", "\tdevicemaps_init(mdesc);\n\ta6_page_devices();\n"),
    ("\tbootmem_init();\n", "\tbootmem_init();\n\ta6_page_bootmem();\n"),
]
for old, new in checks:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate paging checkpoint: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
PY

python3 - "$kernel_head_common" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
replacements = [
    (" THUMB(\tmov\tsp, r3 )\n\tsub\tr2, r1, r0\n",
     " THUMB(\tmov\tsp, r3 )\n\tbl\ta6_post_mmu_marker\n\tsub\tr2, r1, r0\n"),
    ("\tbl\t__memset\t\t\t@ clear .bss\n",
     "\tbl\t__memset\t\t\t@ clear .bss\n\tbl\ta6_post_bss_marker\n"),
    ("\tmov\tlr, #0\n\tb\tstart_kernel\n",
     "\tbl\ta6_post_start_marker\n\tmov\tlr, #0\n\tb\tstart_kernel\n"),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate head-common checkpoint: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
PY

python3 - "$kernel_main" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
rest_anchor = "static __initdata DECLARE_COMPLETION(kthreadd_done);\n"
rest_decls = """extern void a6_rest_pid1(void);
extern void a6_rest_kthread(void);
extern void a6_kinit_enter(void);
extern void a6_kinit_basic(void);
extern void a6_kinit_ramfs(void);
extern void a6_kinit_ready(void);
extern void a6_kinit_exec(void);
extern void a6_kinit_fail(void);

static __initdata DECLARE_COMPLETION(kthreadd_done);
"""
if text.count(rest_anchor) != 1:
    raise SystemExit("could not locate rest_init declaration anchor")
text = text.replace(rest_anchor, rest_decls, 1)

extra_replacements = [
    ("\tpid = kernel_clone(&init_args);\n", "\tpid = kernel_clone(&init_args);\n\ta6_rest_pid1();\n"),
    ("\tpid = kernel_thread(kthreadd, NULL, NULL, CLONE_FS | CLONE_FILES);\n", "\tpid = kernel_thread(kthreadd, NULL, NULL, CLONE_FS | CLONE_FILES);\n\ta6_rest_kthread();\n"),
    ("static int __ref kernel_init(void *unused)\n{\n\tint ret;\n", "static int __ref kernel_init(void *unused)\n{\n\tint ret;\n\n\ta6_kinit_enter();\n"),
    ("\tkernel_init_freeable();\n", "\tkernel_init_freeable();\n\ta6_kinit_ready();\n"),
    ("\tif (ramdisk_execute_command) {\n\t\tret = run_init_process(ramdisk_execute_command);\n", "\tif (ramdisk_execute_command) {\n\t\ta6_kinit_exec();\n\t\tret = run_init_process(ramdisk_execute_command);\n\t\tif (ret) a6_kinit_fail();\n"),
    ("\tdo_basic_setup();\n", "\tdo_basic_setup();\n\ta6_kinit_basic();\n"),
    ("\twait_for_initramfs();\n", "\twait_for_initramfs();\n\ta6_kinit_ramfs();\n"),
]
for old, new in extra_replacements:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate PID 1 checkpoint: {old!r}")
    text = text.replace(old, new, 1)

entry = "asmlinkage __visible __init __no_sanitize_address __noreturn __no_stack_protector\nvoid start_kernel(void)\n"
decls = """extern void a6_stage_stack(void);
extern void a6_stage_cpuid(void);
extern void a6_stage_build(void);
extern void a6_stage_cgroup(void);
extern void a6_stage_irqoff(void);
extern void a6_stage_bootcpu(void);
extern void a6_stage_page(void);
extern void a6_stage_banner(void);
extern void a6_stage_archin(void);
extern void a6_stage_arch(void);
extern void a6_stage_mmearly(void);
extern void a6_stage_percpu(void);
extern void a6_stage_args(void);
extern void a6_stage_mmcore(void);
extern void a6_stage_sched(void);
extern void a6_stage_irq(void);
extern void a6_stage_time(void);
extern void a6_stage_irqon(void);
extern void a6_stage_console(void);
extern void a6_stage_locking(void);
extern void a6_stage_pageset(void);
extern void a6_stage_delay(void);
extern void a6_stage_archfinal(void);
extern void a6_stage_fork(void);
extern void a6_stage_vfs(void);
extern void a6_stage_cgroups(void);
extern void a6_stage_rest(void);

asmlinkage __visible __init __no_sanitize_address __noreturn __no_stack_protector
void start_kernel(void)
"""
if text.count(entry) != 1:
    raise SystemExit("could not locate start_kernel declaration")
text = text.replace(entry, decls, 1)
replacements = [
    ("\tset_task_stack_end_magic(&init_task);\n", "\tset_task_stack_end_magic(&init_task);\n\ta6_stage_stack();\n"),
    ("\tsmp_setup_processor_id();\n", "\tsmp_setup_processor_id();\n\ta6_stage_cpuid();\n"),
    ("\tinit_vmlinux_build_id();\n", "\tinit_vmlinux_build_id();\n\ta6_stage_build();\n"),
    ("\tcgroup_init_early();\n", "\tcgroup_init_early();\n\ta6_stage_cgroup();\n"),
    ("\tearly_boot_irqs_disabled = true;\n", "\tearly_boot_irqs_disabled = true;\n\ta6_stage_irqoff();\n"),
    ("\tboot_cpu_init();\n", "\tboot_cpu_init();\n\ta6_stage_bootcpu();\n"),
    ("\tpage_address_init();\n", "\tpage_address_init();\n\ta6_stage_page();\n"),
    ("\tpr_notice(\"%s\", linux_banner);\n", "\tpr_notice(\"%s\", linux_banner);\n\ta6_stage_banner();\n"),
    ("\tsetup_arch(&command_line);\n", "\ta6_stage_archin();\n\tsetup_arch(&command_line);\n\ta6_stage_arch();\n"),
    ("\tmm_core_init_early();\n", "\tmm_core_init_early();\n\ta6_stage_mmearly();\n"),
    ("\tsetup_per_cpu_areas();\n", "\tsetup_per_cpu_areas();\n\ta6_stage_percpu();\n"),
    ("\tprint_unknown_bootoptions();\n", "\tprint_unknown_bootoptions();\n\ta6_stage_args();\n"),
    ("\tmm_core_init();\n", "\tmm_core_init();\n\ta6_stage_mmcore();\n"),
    ("\tsched_init();\n", "\tsched_init();\n\ta6_stage_sched();\n"),
    ("\tinit_IRQ();\n", "\tinit_IRQ();\n\ta6_stage_irq();\n"),
    ("\ttime_init();\n", "\ttime_init();\n\ta6_stage_time();\n"),
    ("\tearly_boot_irqs_disabled = false;\n\tlocal_irq_enable();\n", "\tearly_boot_irqs_disabled = false;\n\tlocal_irq_enable();\n\ta6_stage_irqon();\n"),
    ("\tconsole_init();\n", "\tconsole_init();\n\ta6_stage_console();\n"),
    ("\tlocking_selftest();\n", "\tlocking_selftest();\n\ta6_stage_locking();\n"),
    ("\tsetup_per_cpu_pageset();\n", "\tsetup_per_cpu_pageset();\n\ta6_stage_pageset();\n"),
    ("\tcalibrate_delay();\n", "\tcalibrate_delay();\n\ta6_stage_delay();\n"),
    ("\tarch_cpu_finalize_init();\n", "\tarch_cpu_finalize_init();\n\ta6_stage_archfinal();\n"),
    ("\tfork_init();\n", "\tfork_init();\n\ta6_stage_fork();\n"),
    ("\tvfs_caches_init();\n", "\tvfs_caches_init();\n\ta6_stage_vfs();\n"),
    ("\tcgroup_init();\n", "\tcgroup_init();\n\ta6_stage_cgroups();\n"),
    ("\trest_init();\n", "\ta6_stage_rest();\n\trest_init();\n"),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate start_kernel checkpoint: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
PY

python3 - "$kernel_exec" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
decl = """extern void a6_exec_bprm(void);
extern void a6_exec_handler(void);
extern void a6_exec_begin(void);
extern void a6_exec_mmap_pre(void);
extern void a6_exec_mmap_ok(void);
extern void a6_exec_ns_ok(void);
extern void a6_exec_sig_ok(void);
extern void a6_exec_thr_ok(void);
extern void a6_exec_perf_ok(void);
extern void a6_exec_cred_ok(void);
extern void a6_exec_done(void);

"""
anchor = "static int exec_binprm(struct linux_binprm *bprm)\n"
if text.count(anchor) != 1:
    raise SystemExit("could not locate exec_binprm")
text = decl + text
replacements = [
    ("static int bprm_execve(struct linux_binprm *bprm)\n{\n\tint retval;\n",
     "static int bprm_execve(struct linux_binprm *bprm)\n{\n\tint retval;\n\n\ta6_exec_bprm();\n"),
    ("\tretval = exec_binprm(bprm);\n", "\ta6_exec_handler();\n\tretval = exec_binprm(bprm);\n"),
    ("int begin_new_exec(struct linux_binprm * bprm)\n{\n\tstruct task_struct *me = current;\n\tint retval;\n",
     "int begin_new_exec(struct linux_binprm * bprm)\n{\n\tstruct task_struct *me = current;\n\tint retval;\n\n\ta6_exec_begin();\n"),
    ("\tretval = exec_mmap(bprm);\n", "\ta6_exec_mmap_pre();\n\tretval = exec_mmap(bprm);\n\ta6_exec_mmap_ok();\n"),
    ("\tretval = exec_task_namespaces();\n", "\tretval = exec_task_namespaces();\n\ta6_exec_ns_ok();\n"),
    ("\tretval = unshare_sighand(me);\n", "\tretval = unshare_sighand(me);\n\ta6_exec_sig_ok();\n"),
    ("\tflush_thread();\n", "\tflush_thread();\n\ta6_exec_thr_ok();\n"),
    ("\tperf_event_exec();\n", "\tperf_event_exec();\n\ta6_exec_perf_ok();\n"),
    ("\tcommit_creds(bprm->cred);\n", "\tcommit_creds(bprm->cred);\n\ta6_exec_cred_ok();\n"),
    ("\treturn 0;\n\nout_unlock:\n", "\ta6_exec_done();\n\treturn 0;\n\nout_unlock:\n"),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate exec checkpoint: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
PY

python3 - "$kernel_elf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
anchor = "static int load_elf_binary(struct linux_binprm *bprm)\n"
decl = """extern void a6_check_magic(void);
extern void a6_check_arch(void);
extern void a6_check_phalloc(void);
extern void a6_check_phread(void);
extern void a6_check_phdone(void);
extern void a6_check_reject(void);
extern void a6_elf_enter(void);
extern void a6_elf_headers(void);
extern void a6_elf_stack(void);
extern void a6_elf_mapped(void);
extern void a6_elf_tables(void);
extern void a6_elf_regs(void);

"""
if text.count(anchor) != 1:
    raise SystemExit("could not locate ELF loader")
text = decl + text
replacements = [
    ('\tif (elf_ex->e_type != ET_EXEC && elf_ex->e_type != ET_DYN)', '\ta6_check_magic();\n\tif (elf_ex->e_type != ET_EXEC && elf_ex->e_type != ET_DYN)'),
    ('\telf_phdata = load_elf_phdrs(elf_ex, bprm->file);', '\ta6_check_arch();\n\telf_phdata = load_elf_phdrs(elf_ex, bprm->file);'),
    ('\telf_phdata = kmalloc(size, GFP_KERNEL);', '\ta6_check_phalloc();\n\telf_phdata = kmalloc(size, GFP_KERNEL);'),
    ('\tretval = elf_read(elf_file, elf_phdata, size, elf_ex->e_phoff);', '\ta6_check_phread();\n\tretval = elf_read(elf_file, elf_phdata, size, elf_ex->e_phoff);\n\ta6_check_phdone();'),
    ('\tretval = 0;\nout:\n\treturn retval;', '\tretval = 0;\nout:\n\tif (retval) a6_check_reject();\n\treturn retval;'),
    ("\tstruct pt_regs *regs;\n\n\tretval = -ENOEXEC;", "\tstruct pt_regs *regs;\n\n\ta6_elf_enter();\n\tretval = -ENOEXEC;"),
    ("\telf_phdata = load_elf_phdrs(elf_ex, bprm->file);\n\tif (!elf_phdata)\n\t\tgoto out;\n", "\telf_phdata = load_elf_phdrs(elf_ex, bprm->file);\n\tif (!elf_phdata)\n\t\tgoto out;\n\ta6_elf_headers();\n"),
    ("\tretval = setup_arg_pages(bprm, randomize_stack_top(STACK_TOP),\n\t\t\t\t executable_stack);\n\tif (retval < 0)\n\t\tgoto out_free_dentry;\n", "\tretval = setup_arg_pages(bprm, randomize_stack_top(STACK_TOP),\n\t\t\t\t executable_stack);\n\tif (retval < 0)\n\t\tgoto out_free_dentry;\n\ta6_elf_stack();\n"),
    ("\tretval = create_elf_tables(bprm, elf_ex, interp_load_addr,\n\t\t\t\t   e_entry, phdr_addr);\n", "\ta6_elf_mapped();\n\tretval = create_elf_tables(bprm, elf_ex, interp_load_addr,\n\t\t\t\t   e_entry, phdr_addr);\n"),
    ("\tif (retval < 0)\n\t\tgoto out;\n\n\tmm = current->mm;", "\tif (retval < 0)\n\t\tgoto out;\n\ta6_elf_tables();\n\n\tmm = current->mm;"),
    ("\tSTART_THREAD(elf_ex, regs, elf_entry, bprm->p);\n", "\tSTART_THREAD(elf_ex, regs, elf_entry, bprm->p);\n\ta6_elf_regs();\n"),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"could not locate ELF checkpoint: {old!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
PY

python3 - "$kernel_traps" "$kernel_fault" <<'PY'
from pathlib import Path
import sys

decl = "extern void a6_fault_undef(void);\nextern void a6_fault_memory(void);\n"
edits = [
    ("asmlinkage void do_undefinstr(struct pt_regs *regs)\n{\n",
     "asmlinkage void do_undefinstr(struct pt_regs *regs)\n{\n\ta6_fault_undef();\n"),
    ("void do_bad_area(unsigned long addr, unsigned int fsr, struct pt_regs *regs)\n{\n",
     "void do_bad_area(unsigned long addr, unsigned int fsr, struct pt_regs *regs)\n{\n\ta6_fault_memory();\n"),
]
for filename, (old, new) in zip(sys.argv[1:], edits):
    path = Path(filename)
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"could not locate fault handler in {filename}")
    path.write_text(decl + text.replace(old, new, 1))
PY

python3 - "$kernel_entry_common" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
old = "no_work_pending:\n\tasm_trace_hardirqs_on save = 0\n"
new = "no_work_pending:\n\tbl\ta6_user_return\n\tasm_trace_hardirqs_on save = 0\n"
if text.count(old) != 1:
    raise SystemExit("could not locate return-to-userspace path")
text = text.replace(old, new, 1)
old = "\treload_current r10, ip\n\tzero_fp\n"
new = "\tbl\ta6_user_svc\n\treload_current r10, ip\n\tzero_fp\n"
if text.count(old) != 1:
    raise SystemExit("could not locate SVC entry path")
path.write_text(text.replace(old, new, 1))
PY

python3 - "$kernel_read_write" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
anchor = "SYSCALL_DEFINE3(write, unsigned int, fd, const char __user *, buf,\n\t\tsize_t, count)\n{\n\treturn ksys_write(fd, buf, count);\n}"
replacement = """extern void a6_userspace_syscall(void);

SYSCALL_DEFINE3(write, unsigned int, fd, const char __user *, buf,
		size_t, count)
{
	/* Bring-up proof: reaching here requires an ARM userspace SVC, syscall
	 * dispatch, and execution in PID 1 after execve(/init). */
	a6_userspace_syscall();
	return ksys_write(fd, buf, count);
}"""
if text.count(anchor) != 1:
    raise SystemExit("could not locate write syscall")
path.write_text(text.replace(anchor, replacement, 1))
PY

python3 - "$kernel_exec" "$kernel_context" <<'PY'
from pathlib import Path
import sys
decl = 'extern void a6_mm_state(void);\nextern void a6_mm_lock(void);\nextern void a6_mm_activate(void);\nextern void a6_mm_vmalloc(void);\nextern void a6_mm_reserved(void);\nextern void a6_mm_asid(void);\nextern void a6_mm_switched(void);\n'
changes = [[('\tmm_exit_exec_release(tsk, old_mm);', '\ta6_mm_state();\n\tmm_exit_exec_release(tsk, old_mm);'), ('\ttask_lock(tsk);\n\tmembarrier_exec_mmap(mm);', '\ta6_mm_lock();\n\ttask_lock(tsk);\n\tmembarrier_exec_mmap(mm);'), ('\tactivate_mm(active_mm, mm);', '\ta6_mm_activate();\n\tactivate_mm(active_mm, mm);')], [('\tcheck_vmalloc_seq(mm);', '\tcheck_vmalloc_seq(mm);\n\ta6_mm_vmalloc();'), ('\tcpu_set_reserved_ttbr0();', '\tcpu_set_reserved_ttbr0();\n\ta6_mm_reserved();'), ('\tcpu_switch_mm(mm->pgd, mm);', '\ta6_mm_asid();\n\tcpu_switch_mm(mm->pgd, mm);\n\ta6_mm_switched();')]]
for filename, edits in zip(sys.argv[1:], changes):
    p = Path(filename)
    t = p.read_text()
    for old, new in edits:
        if t.count(old) != 1:
            raise SystemExit(f"ambiguous MM checkpoint: {old!r}")
        t = t.replace(old, new, 1)
    p.write_text(decl + t)
PY

if [[ "${A6_ROLLOVER_TLBI:-0}" == 1 ]]; then
    [[ "${A6_LOCAL_RANGE_TLBI:-0}" == 1 ]]
    python3 "$repo_root/scripts/instrument-a6-rollover-tlbi.py" "$kernel_context" "${A6_LOCAL_FULL_TLBI:-0}" "${A6_ROLLOVER_DEFERRED_LOG:-0}"
fi

# The next hardware image is observational only. Keep the selected A6
# cache/MMU implementation above unchanged, but replace the older full-screen
# and text diagnostics with a six-block append-only handoff ledger.
python3 - "$compressed_head" "$kernel_head" <<'PY'
from pathlib import Path
import re

compressed = Path(__import__("sys").argv[1])
kernel_head = Path(__import__("sys").argv[2])

ledger = """\t\t/* Append-only A6 handoff ledger: six 32x8 blocks. */
\t\t.macro a6_ledger_mark stage
\t\tpush\t{r0-r12, lr}
\t\tmrs\tr12, cpsr
\t\tpush\t{r12}
\t\tmov\tr0, #\\stage
\t\tldr\tr1, =0x83fff000
\t\tldr\tr4, [r1]
\t\tldr\tr5, [r1, #8]
\t\tmov\tr2, #40
\t\tmul\tr2, r0, r2
\t\tadd\tr4, r4, r2, lsl #2
\t\tmov\tr6, #8
\t\tmovw\tr12, #0xffff
\t\tmovt\tr12, #0x00ff
1:\t\tmov\tr7, r4
\t\tmov\tr8, #32
\t\tmov\tr9, #0
2:\t\teor\tr10, r0, r6
\t\teor\tr10, r10, r9
\t\ttst\tr10, #1
\t\tmoveq\tr10, r12
\t\tmovne\tr10, #0
\t\tstr\tr10, [r7], #4
\t\tadd\tr9, r9, #1
\t\tsubs\tr8, r8, #1
\t\tbne\t2b
\t\tadd\tr4, r4, r5
\t\tsubs\tr6, r6, #1
\t\tbne\t1b
\t\tdsb\tsy
\t\tpop\t{r12}
\t\tmsr\tcpsr_f, r12
\t\tpop\t{r0-r12, lr}
\t\t.endm
"""

decomp_ns = """\t\t.macro a6_ledger_mark_nostack stage
\t\tldr\tr1, =0x83fff000
\t\tstr\tr7, [r1, #0x10]
\t\tstr\tr8, [r1, #0x14]
\t\tstr\tr9, [r1, #0x1c]
\t\tmrs\tr2, cpsr
\t\tstr\tr2, [r1, #0x18]
\t\tmov\tr0, #\\stage
\t\tldr\tr4, [r1]
\t\tldr\tr5, [r1, #8]
\t\tmov\tr2, #40
\t\tmul\tr2, r0, r2
\t\tadd\tr4, r4, r2, lsl #2
\t\tmov\tr6, #8
\t\tmovw\tr12, #0xffff
\t\tmovt\tr12, #0x00ff
3:\t\tmov\tr7, r4
\t\tmov\tr8, #32
\t\tmov\tr9, #0
4:\t\teor\tr10, r0, r6
\t\teor\tr10, r10, r9
\t\ttst\tr10, #1
\t\tmoveq\tr10, r12
\t\tmovne\tr10, #0
\t\tstr\tr10, [r7], #4
\t\tadd\tr9, r9, #1
\t\tsubs\tr8, r8, #1
\t\tbne\t4b
\t\tadd\tr4, r4, r5
\t\tsubs\tr6, r6, #1
\t\tbne\t3b
\t\tdsb\tsy
\t\tldr\tr1, =0x83fff000
\t\tldr\tr7, [r1, #0x10]
\t\tldr\tr8, [r1, #0x14]
\t\tldr\tr9, [r1, #0x1c]
\t\tldr\tr2, [r1, #0x18]
\t\tmsr\tcpsr_f, r2
\t\tmov\tr0, #0
\t\t.endm
"""

kernel_ns = """\t\t.macro a6_ledger_mark_kernel stage
\t\tldr\tr3, =0x83fff000
\t\tstr\tr0, [r3, #0x10]
\t\tstr\tr1, [r3, #0x14]
\t\tstr\tr2, [r3, #0x18]
\t\tmrs\tr12, cpsr
\t\tstr\tr12, [r3, #0x1c]
\t\tmov\tr0, #\\stage
\t\tldr\tr4, [r3]
\t\tldr\tr5, [r3, #8]
\t\tmov\tr2, #40
\t\tmul\tr2, r0, r2
\t\tadd\tr4, r4, r2, lsl #2
\t\tmov\tr6, #8
\t\tmovw\tr12, #0xffff
\t\tmovt\tr12, #0x00ff
5:\t\tmov\tr7, r4
\t\tmov\tr8, #32
\t\tmov\tr9, #0
6:\t\teor\tr10, r0, r6
\t\teor\tr10, r10, r9
\t\ttst\tr10, #1
\t\tmoveq\tr10, r12
\t\tmovne\tr10, #0
\t\tstr\tr10, [r7], #4
\t\tadd\tr9, r9, #1
\t\tsubs\tr8, r8, #1
\t\tbne\t6b
\t\tadd\tr4, r4, r5
\t\tsubs\tr6, r6, #1
\t\tbne\t5b
\t\tdsb\tsy
\t\tldr\tr3, =0x83fff000
\t\tldr\tr0, [r3, #0x10]
\t\tldr\tr1, [r3, #0x14]
\t\tldr\tr2, [r3, #0x18]
\t\tldr\tr12, [r3, #0x1c]
\t\tmsr\tcpsr_f, r12
\t\t.endm
"""

text = compressed.read_text()
if "Append-only A6 handoff ledger" not in text:
    marker = "start:\n"
    if text.count(marker) != 1:
        raise SystemExit("ledger: compressed start not unique")
    text = text.replace(marker, ledger + decomp_ns + marker, 1)

if "a6_ledger_mark_nostack 0" not in text:
    pattern = r"(\t\tmov\tr7, r1[^\n]*\n\t\tmov\tr8, r2[^\n]*\n)"
    text, n = re.subn(pattern, r"\1\t\ta6_ledger_mark_nostack 0\t\t@ D0: decompressor entered\n", text, count=1)
    if n != 1:
        raise SystemExit("ledger: D0 insertion failed")

pattern = r"(\t\tbl\tdecompress_kernel\n).*?(\n\t\tget_inflated_image_size\tr1, r2, r3\n)"
text, n = re.subn(pattern, r"\1\n\t\ta6_ledger_mark 1\t\t@ D1: decompression returned\2", text, count=1, flags=re.S)
if n != 1:
    raise SystemExit("ledger: D1 replacement failed")

start = text.find("\t\tget_inflated_image_size\tr1, r2, r3\n")
end = text.find("\n#ifdef CONFIG_ARM_VIRT_EXT", start)
if start < 0 or end < 0:
    raise SystemExit("ledger: final handoff region not found")
region = text[start:end]
pattern = r"\t\tbl\tcache_clean_flush\n.*?\t\tbl\tcache_off\n.*"
replacement = ("\t\ta6_ledger_mark 2\t\t@ H0: before handoff maintenance\n"
               "\t\tbl\tcache_clean_flush\n"
               "\t\tbl\tcache_off\n"
               "\t\ta6_ledger_mark 3\t\t@ H1: handoff maintenance returned\n")
region, n = re.subn(pattern, replacement, region, count=1, flags=re.S)
if n != 1:
    raise SystemExit("ledger: H0/H1 replacement failed")
text = text[:start] + region + text[end:]

needle = "#else\n\t\tb\t__enter_kernel\n"
if text.count(needle) != 1:
    raise SystemExit("ledger: J0 branch not unique")
text = text.replace(needle, "#else\n\t\ta6_ledger_mark 4\t\t@ J0: immediately before branch\n\t\tb\t__enter_kernel\n", 1)
compressed.write_text(text)

kt = kernel_head.read_text()
if "Append-only A6 handoff ledger" not in kt:
    marker = "ENTRY(stext)\n"
    if kt.count(marker) != 1:
        raise SystemExit("ledger: kernel entry not unique")
    kt = kt.replace(marker, ledger + kernel_ns + marker, 1)
kt = re.sub(r"\.macro a6_paint low, high\n.*?\.endm", ".macro a6_paint low, high\n.endm", kt, count=1, flags=re.S)
kt = re.sub(r"\.macro a6_text label\n.*?\.endm", ".macro a6_text label\n.endm", kt, count=1, flags=re.S)
kt = re.sub(r"\.macro a6_visible_stage name, low, high, message\n.*?\.endm",
            lambda _m: ".macro a6_visible_stage name, low, high, message\n\\name:\n\\tbx\\tlr\n.endm",
            kt, count=1, flags=re.S)
kt = re.sub(r"\.macro a6_quick_stage name, low, high\n.*?\.endm",
            lambda _m: ".macro a6_quick_stage name, low, high\n\\name:\n\\tbx\\tlr\n.endm",
            kt, count=1, flags=re.S)
bs = chr(92)
kt = kt.replace(bs + bs + "name:", bs + "name:")
kt = kt.replace(bs + bs + "tbx" + bs + bs + "tlr", bs + "tbx" + bs + "tlr")
kt = kt.replace(bs + "tbx" + bs + "tlr", "\tbx\tlr")
stage_stub = (".global " + bs + "name\n"
              ".type " + bs + "name, %function\n"
              + bs + "name:\n\tbx\tlr\n.endm")
kt = re.sub(r"\.macro a6_visible_stage name, low, high, message\n.*?\.endm",
            lambda _m: ".macro a6_visible_stage name, low, high, message\n" + stage_stub,
            kt, count=1, flags=re.S)
kt = re.sub(r"\.macro a6_quick_stage name, low, high\n.*?\.endm",
            lambda _m: ".macro a6_quick_stage name, low, high\n" + stage_stub,
            kt, count=1, flags=re.S)
kt = kt.replace("\ta6_paint 0x00ff, 0x00ff\n",
                "\ta6_ledger_mark_kernel 5\t\t@ K0: first instruction at destination\n", 1)
kernel_head.write_text(kt)
PY

if [[ "$usb_boot_status" == 1 ]]; then
	python3 "$repo_root/scripts/instrument-a6-boot-status.py" "$repo_root" "$linux_root"
fi
if [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
    [[ ! -e "$linux_root/drivers/irqchip/a6-smp.c" ]]
    clang --target=arm-none-eabi -mcpu=swift -marm -ffreestanding -nostdlib \
        -I "$repo_root/kernel/platform" -c "$repo_root/boot/arm/a6-smp-secondary.S" \
        -o "$output_root/a6-smp-secondary.o"
    llvm-objcopy -O binary --only-section=.text.a6_smp_bridge \
        "$output_root/a6-smp-secondary.o" "$output_root/a6-smp-secondary.bin"
    python3 "$repo_root/scripts/a6-smp-bridge-blob.py" \
        "$output_root/a6-smp-secondary.o" "$output_root/a6-smp-secondary.bin" \
        "$output_root/a6-smp-bridge-blob.h"
    python3 "$repo_root/scripts/patch-a6-smp-bridge.py" "$repo_root" "$linux_root" "$output_root"
fi

make_args=(
	-C "$linux_root"
	O="$output_root"
	ARCH=arm
	LLVM=1
	LLVM_IAS=1
	CFLAGS_samsung_tty.o=-DA6_S5L_UART_BRINGUP
)

make "${make_args[@]}" tinyconfig
KCONFIG_CONFIG="$output_root/.config" \
	"$linux_root/scripts/kconfig/merge_config.sh" \
	-m -O "$output_root" "$output_root/.config" "$fragment"
make "${make_args[@]}" olddefconfig
if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
    if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
        python3 - "$repo_root" "$linux_root" <<'PY_NATIVE'
import importlib.util,sys
from pathlib import Path
repo,linux=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('native',repo/'scripts/prepare-a6-brcmfmac-n42.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=linux/m.USB;p.write_text(m.render(p.read_text()))
(p.parent/'a6_hsic.h').write_text((repo/'kernel/platform/brcmfmac-a6-hsic.h').read_text())
PY_NATIVE
        python3 "$repo_root/scripts/patch-a6-native-execmem.py" "$linux_root"
        printf '\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_NATIVE=1\n' >> "$linux_root/drivers/usb/host/Makefile"
    fi
    python3 "$repo_root/scripts/patch-a6-ehci-trial.py" "$linux_root"
    cp "$repo_root/kernel/platform/ehci-a6-trial.c" "$linux_root/drivers/usb/host/ehci-a6-trial.c"
    cp "$repo_root/kernel/platform/a6-wifi-usb-bulk-rx.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-bulk-rx.inc"
    cp "$repo_root/kernel/platform/a6-wifi-usb-loopback.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-loopback.inc"
    cp "$repo_root/kernel/platform/brcmfmac-a6-hsic.h" "$linux_root/drivers/usb/host/brcmfmac-a6-hsic.h"
    cp "$repo_root/kernel/platform/a6-wifi-usb-runtime.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-runtime.inc"
    cp "$repo_root/kernel/platform/a6-wifi-usb-scan.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-scan.inc"
    cp "$repo_root/kernel/platform/a6-wifi-scan-codec.h" "$linux_root/drivers/usb/host/a6-wifi-scan-codec.h"
    cp "$repo_root/kernel/platform/a6-wifi-usb-preflight.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-preflight.inc"
    cp "$repo_root/kernel/platform/a6-wifi-usb-download.inc" "$linux_root/drivers/usb/host/a6-wifi-usb-download.inc"
    printf '\nobj-$(CONFIG_USB_EHCI_HCD) += ehci-a6-trial.o\n' >> "$linux_root/drivers/usb/host/Makefile"
    if [[ "${A6_WIFI_USB_IDENTITY:-0}" == 1 ]]; then
        printf '\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_IDENTITY=1\n' >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_OTP:-0}" == 1 ]]; then
        printf '\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_OTP=1\n' >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_RX:-0}" == 1 ]]; then
        printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_RX=1\n" >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_LOOPBACK:-0}" == 1 ]]; then
        printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_LOOPBACK=1 -Oz\n" >> "$linux_root/drivers/usb/host/Makefile"
        if [[ "${A6_WIFI_USB_LOOPBACK_BAD_CHECKSUM:-0}" == 1 ]]; then
            printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_LOOPBACK_BAD_CHECKSUM=1\n" >> "$linux_root/drivers/usb/host/Makefile"
        fi
    fi
    if [[ "${A6_WIFI_USB_SCAN:-0}" == 1 ]]; then
        printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_SCAN=1 -Oz -Wno-unused-function\n" >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_COUNTRY:-0}" == 1 ]]; then
        printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_COUNTRY=1\n" >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_PREFLIGHT:-0}" == 1 ]]; then
        printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_PREFLIGHT=1 -Oz\n" >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_RUNTIME:-0}" == 1 ]]; then
        printf "\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_RUNTIME=1\n" >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_EXECUTE:-0}" == 1 ]]; then
        printf '\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_EXECUTE=1\n' >> "$linux_root/drivers/usb/host/Makefile"
    fi
    if [[ "${A6_WIFI_USB_DOWNLOAD:-0}" == 1 ]]; then
        printf '\nCFLAGS_ehci-a6-trial.o += -DA6_WIFI_USB_DOWNLOAD=1 -DA6_WIFI_FW_BYTES=%s -DA6_WIFI_FW_CRC32=%s\n' "$a6_wifi_bytes" "$a6_wifi_crc" >> "$linux_root/drivers/usb/host/Makefile"
        "$linux_root/scripts/config" --file "$output_root/.config" --enable FW_LOADER --disable FW_LOADER_USER_HELPER
    fi
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable USB --enable USB_EHCI_HCD --disable USB_EHCI_HCD_PLATFORM \
        --disable USB_STORAGE --disable USB_HID --disable BRCMFMAC
fi
if [[ "$usb_console" == 1 ]]; then
	"$linux_root/scripts/config" --file "$output_root/.config" \
		--enable USB_SUPPORT --enable USB_GADGET --enable USB_DWC2 \
		--enable USB_DWC2_PERIPHERAL --enable GENERIC_PHY \
		--enable USB_G_SERIAL --enable U_SERIAL_CONSOLE \
		--enable DEVTMPFS --enable PRINTK --enable BINFMT_ELF \
		--enable SYSFS --enable PROC_FS \
		--set-str CMDLINE "earlycon=apple,s5l-uart,0x32600000 console=ttySAC0,115200 console=ttyGS0 loglevel=8 panic=0 lpj=1000000 g_serial.use_acm=1 g_serial.idVendor=0x1209 g_serial.idProduct=0x0001"
	# Fold in the proven prepare_page_table framebuffer-preservation fix.
	# The loop below MODULES_VADDR must also preserve the bf600000 PMD.
	sed -i 's/addr >= 0x83000000UL \&\& addr < 0x85000000UL/(addr >= 0x83000000UL \&\& addr < 0x85000000UL) || addr >= 0xbf600000UL/' "$kernel_mmu"
fi
if [[ "${A6_USB_NETWORK:-0}" == 1 ]]; then
    smp_cpu0_cap=""
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
        smp_cpu0_cap=" maxcpus=1"
    elif [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        smp_cpu0_cap=" maxcpus=2"
    fi
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable NET --enable INET --disable IPV6 \
        --disable USB_G_SERIAL --enable USB_CDC_COMPOSITE \
        --set-str CMDLINE "earlycon=apple,s5l-uart,0x32600000 console=ttySAC0,115200 console=ttyGS0 loglevel=8 panic=0 lpj=1000000 g_cdc.host_addr=02:00:00:06:00:01 g_cdc.dev_addr=02:00:00:06:00:02${smp_cpu0_cap}"
fi
if [[ "${A6_D1972_POWER_SUPPLY:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" --enable POWER_SUPPLY
fi
"$linux_root/scripts/config" --file "$output_root/.config" \
	--enable BLK_DEV_INITRD \
	--set-str INITRAMFS_SOURCE "$initramfs_list"
make "${make_args[@]}" olddefconfig
if [[ "${A6_USB_SHELL:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable FUTEX --enable COMPAT_32BIT_TIME
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_VFP:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable VFP --enable VFPv3 --enable NEON
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_ARCH_USERSPACE:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable UNIX --enable EPOLL --enable SIGNALFD --enable TIMERFD \
        --enable EVENTFD --enable INOTIFY_USER --enable POSIX_TIMERS \
        --enable SYSVIPC --enable TMPFS --enable UNIX98_PTYS
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_FRAMEBUFFER:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable FB --enable FB_A6_BOOT --disable FRAMEBUFFER_CONSOLE
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_XORG_CREDENTIALS:-0}" == 1 ]]; then
    # Xorg Popen drops credentials before executing xkbcomp. Without this,
    # setgid/setuid return ENOSYS and its child exits 127.
    "$linux_root/scripts/config" --file "$output_root/.config" --enable MULTIUSER
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_WAYLAND_LOCKS:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" --enable FILE_LOCKING
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_RAM_ROOT_COMPONENTS:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable BLOCK --enable BLK_DEV --enable BLK_DEV_LOOP --enable MISC_FILESYSTEMS \
        --enable SQUASHFS --enable SQUASHFS_ZSTD --enable OVERLAY_FS --enable TMPFS_XATTR \
        --enable SWAP --enable ZSMALLOC --enable ZRAM --enable ZRAM_BACKEND_LZ4 --enable ZRAM_DEF_COMP_LZ4 \
        --disable ZRAM_WRITEBACK --disable KEXEC
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_RAM_ROOT_XZ:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --disable INITRAMFS_COMPRESSION_GZIP --enable INITRAMFS_COMPRESSION_XZ --enable RD_XZ
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable DRM --enable DRM_SIMPLEDRM --disable DRM_FBDEV_EMULATION \
        --enable INPUT_EVDEV --enable INPUT_MISC --enable INPUT_UINPUT \
        --disable DRM_CLIENT_LOG --disable DRM_CLIENT_LIB \
        --disable KERNEL_GZIP --enable KERNEL_XZ
    make "${make_args[@]}" olddefconfig
fi
if [[ "${A6_SMP_COMPILE_ONLY:-0}" == 1 ]]; then
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
        [[ "$output_root" == *-smp-cpu0-only ]]
    elif [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        if [[ "${A6_SMP_SCHEDULING:-0}" == 1 ]]; then
            [[ "$output_root" == *-smp-first-scheduling ]]
        else
            if [[ "${A6_SMP_TIMER_LINE_PROBE:-0}" == 1 ]]; then
                [[ "$output_root" == *-smp-timer-line-checkpoint ]]
            else
                [[ "$output_root" == *-smp-bridge-quarantine ]]
            fi
        fi
    else
        [[ "$output_root" == *-smp-compile-only ]]
    fi
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable SMP --set-val NR_CPUS 2 --disable HOTPLUG_CPU \
        --disable CPU_IDLE --disable PERF_EVENTS --disable ARM_PMU
    make "${make_args[@]}" olddefconfig
    rg -q '^CONFIG_SMP=y$' "$output_root/.config"
    rg -q '^CONFIG_NR_CPUS=2$' "$output_root/.config"
    rg -q '^CONFIG_GENERIC_IRQ_IPI_MUX=y$' "$output_root/.config"
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
        rg -q '^CONFIG_CMDLINE="[^"]* maxcpus=1"$' "$output_root/.config"
        rg -q '^CONFIG_CMDLINE_FORCE=y$' "$output_root/.config"
    fi
fi
if [[ "${A6_RAM_ROOT:-0}" == 1 ]]; then
    KCONFIG_CONFIG="$output_root/.config" \
        "$linux_root/scripts/kconfig/merge_config.sh" -m -O "$output_root" \
        "$output_root/.config" "$repo_root/kernel/a6-ram-root.config"
    make "${make_args[@]}" olddefconfig
    for feature in BLOCK BLK_DEV_LOOP SQUASHFS SQUASHFS_ZSTD OVERLAY_FS \
        TMPFS_XATTR SWAP ZSMALLOC ZRAM ZRAM_BACKEND_LZ4 ZRAM_DEF_COMP_LZ4; do
        rg -q "^CONFIG_${feature}=y$" "$output_root/.config"
    done
    rg -q '^# CONFIG_ZRAM_WRITEBACK is not set$' "$output_root/.config"
fi
if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
    # Apply after diagnostic/profile defaults and NET; Kconfig otherwise drops
    # wireless tristates while NET is still disabled in tinyconfig.
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --enable MODULES --enable MODULE_UNLOAD --enable ARM_MODULE_PLTS --enable NETDEVICES \
        --enable WIRELESS --enable WLAN --enable WLAN_VENDOR_BROADCOM \
        --module CFG80211 --module BRCMFMAC --enable BRCMFMAC_USB --disable BRCMFMAC_SDIO \
        --disable BRCMFMAC_PCIE --disable BRCMFMAC_PROTO_MSGBUF --disable CFG80211_WEXT \
        --enable CFG80211_REQUIRE_SIGNED_REGDB --enable CFG80211_USE_KERNEL_REGDB_KEYS \
        --module CRYPTO_SHA256 --module PACKET --disable RFKILL \
        --enable NETFILTER --module NF_CONNTRACK --module NF_TABLES \
        --enable NF_TABLES_IPV4 --module NFT_CT --module INET_UDP_DIAG --disable IPV6 \
        --enable SECCOMP --enable SECCOMP_FILTER --enable STACKPROTECTOR --enable STACKPROTECTOR_STRONG \
        --enable FORTIFY_SOURCE --enable HARDENED_USERCOPY
    case "${A6_BROWSER_SANDBOX:-0}" in
        0) ;;
        1)
            # Firefox's normal Linux sandbox requires unprivileged user
            # namespaces as well as the existing seccomp configuration.
            "$linux_root/scripts/config" --file "$output_root/.config" \
                --enable NAMESPACES --enable USER_NS --enable PID_NS \
                --enable IPC_NS --enable UTS_NS --enable NET_NS \
                --enable CGROUPS --enable MEMCG --enable PSI
            ;;
        *) echo 'A6_BROWSER_SANDBOX must be 0 or 1' >&2; exit 1;;
    esac
    case "${A6_RAM_MIB:-768}" in
        768) ;;
        944)
            [[ "${A6_BROWSER_SANDBOX:-0}" == 1 ]]
            # 3G/1G ARM lowmem: 1008MiB -64MiB vmalloc =944MiB.
            # Keep HIGHMEM off and the tested userspace address-space split.
            python3 - "$output_root/.config" <<'PY_BROWSER_RAM'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]);s=p.read_text()
assert 'vmalloc=' not in s
s,n=re.subn(r'(^CONFIG_CMDLINE="[^"\n]*)"$',r'\1 vmalloc=64M"',s,flags=re.M)
assert n==1
p.write_text(s)
PY_BROWSER_RAM
            ;;
        *) echo 'A6_RAM_MIB must be 768 or 944' >&2; exit 1;;
    esac
    # The shell opens ttyGS0 explicitly. Keep printk in the RAM log buffer,
    # without a second request stream/console worker sharing its USB gadget.
    "$linux_root/scripts/config" --file "$output_root/.config" \
        --disable U_SERIAL_CONSOLE --enable NULL_TTY
    python3 - "$output_root/.config" <<'PY_WIFI_RAM_CONSOLE'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]);s=p.read_text()
s,n=re.subn(r'(^CONFIG_CMDLINE=")earlycon=apple,s5l-uart,0x32600000 console=ttySAC0,115200 console=ttyGS0 ',
            r'\1console=ttynull ',s,flags=re.M)
assert n==1
p.write_text(s)
PY_WIFI_RAM_CONSOLE
    # Isolate hardening added with the firewall image from pre-HSIC USB stalls.
    # Default remains hardened; diagnostic builds cannot be promoted connected.
    if [[ "${A6_WIFI_HARDENING:-1}" == 0 ]]; then
        "$linux_root/scripts/config" --file "$output_root/.config" \
            --disable STACKPROTECTOR --disable STACKPROTECTOR_STRONG \
            --disable FORTIFY_SOURCE --disable HARDENED_USERCOPY
    else
        [[ "${A6_WIFI_HARDENING:-1}" == 1 ]]
    fi
    # Diagnostic control for USB stalls reproduced before HSIC startup. Keep
    # the SMP kernel/DT intact but optionally leave CPU1 unstarted; forced
    # kernel command line takes precedence over the two-CPU DT bootargs.
    if [[ "${A6_WIFI_BOOT_CPUS:-2}" == 1 ]]; then
        python3 - "$output_root/.config" <<'PY_WIFI_BOOT_CPUS'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]);s=p.read_text()
s,n=re.subn(r'(^CONFIG_CMDLINE="[^\n]* maxcpus=)2("$)',r'\g<1>1\2',s,flags=re.M)
assert n==1 and 'CONFIG_CMDLINE_FORCE=y' in s
p.write_text(s)
PY_WIFI_BOOT_CPUS
    else
        [[ "${A6_WIFI_BOOT_CPUS:-2}" == 2 ]]
    fi
    make "${make_args[@]}" olddefconfig
    if [[ "${A6_AUDIO_ALSA:-0}" == 1 ]]; then
        "$linux_root/scripts/config" --file "$output_root/.config" -e SOUND -e SND -e A6_AUDIO_ALSA -e SND_PCM -e SND_TIMER -e HIGH_RES_TIMERS -d INITRAMFS_COMPRESSION_XZ -e INITRAMFS_COMPRESSION_NONE
        make "${make_args[@]}" olddefconfig
        rg -q '^CONFIG_SND_PCM=y$' "$output_root/.config"
        rg -q '^CONFIG_A6_AUDIO_ALSA=y$' "$output_root/.config"
        rg -q '^CONFIG_HIGH_RES_TIMERS=y$' "$output_root/.config"
    fi
    rg -q '^CONFIG_NULL_TTY=y$' "$output_root/.config"
    ! rg -q '^CONFIG_U_SERIAL_CONSOLE=y$' "$output_root/.config"
    for setting in CONFIG_CFG80211=m CONFIG_BRCMFMAC=m CONFIG_BRCMFMAC_USB=y CONFIG_MODULE_UNLOAD=y CONFIG_ARM_MODULE_PLTS=y CONFIG_NETFILTER=y CONFIG_NF_TABLES=m CONFIG_NF_CONNTRACK=m CONFIG_NFT_CT=m CONFIG_SECCOMP=y CONFIG_SECCOMP_FILTER=y; do
        rg -q "^$setting$" "$output_root/.config" || { echo "Missing native setting: $setting" >&2; exit 1; }
    done
    if [[ "${A6_WIFI_HARDENING:-1}" == 1 ]]; then
        for setting in CONFIG_STACKPROTECTOR_STRONG=y CONFIG_FORTIFY_SOURCE=y CONFIG_HARDENED_USERCOPY=y; do
            rg -q "^$setting$" "$output_root/.config" || { echo "Missing hardening: $setting" >&2; exit 1; }
        done
    else
        for setting in STACKPROTECTOR FORTIFY_SOURCE HARDENED_USERCOPY; do
            ! rg -q "^CONFIG_$setting=y$" "$output_root/.config" || exit 1
        done
    fi
    if [[ "${A6_BROWSER_SANDBOX:-0}" == 1 ]]; then
        for feature in NAMESPACES USER_NS PID_NS IPC_NS UTS_NS NET_NS CGROUPS MEMCG PSI; do
            rg -q "^CONFIG_${feature}=y$" "$output_root/.config" || { echo "Missing browser sandbox namespace: $feature" >&2; exit 1; }
        done
    fi
fi
if [[ "${A6_INCREMENTAL_BUILD:-0}" == 1 ]]; then
    python3 "$repo_root/scripts/a6-kbuild-cache.py" restore "$linux_root" "$output_root"
fi
make "${make_args[@]}" -j"${A6_BUILD_JOBS:-$(nproc)}" zImage
if [[ "${A6_AUDIO_ALSA:-0}" == 1 ]]; then
    # The proven decompressor maps eight output sections as noncacheable.
    # One outer XZ stream avoids recompressing an embedded XZ archive.
    rg -q '^CONFIG_INITRAMFS_COMPRESSION_NONE=y$' "$output_root/.config"
    python3 - "$output_root/arch/arm/boot/Image" <<'CHECK_AUDIO_IMAGE'
from pathlib import Path
import sys
assert Path(sys.argv[1]).stat().st_size + 0x8000 < 8 * 1024 * 1024
CHECK_AUDIO_IMAGE
fi

if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then
    make "${make_args[@]}" -j"${A6_BUILD_JOBS:-$(nproc)}" modules
    mkdir -p "$repo_root/build/wifi-native/modules"
    find "$output_root/net/wireless" "$output_root/drivers/net/wireless/broadcom" \
        "$output_root/net/netfilter" "$output_root/net/ipv4/netfilter" \
        -name '*.ko' -exec cp '{}' "$repo_root/build/wifi-native/modules/" \;
    # Signed regulatory.db verification needs the Crypto API SHA-256 module.
    cp "$output_root/crypto/sha256.ko" "$repo_root/build/wifi-native/modules/"
    cp "$output_root/net/ipv4/udp_diag.ko" "$repo_root/build/wifi-native/modules/"
    cp "$output_root/net/packet/af_packet.ko" "$repo_root/build/wifi-native/modules/"
    tar -C "$repo_root/build/wifi-native" -czf "$repo_root/build/wifi-native/modules.tar.gz" modules
    cp "$output_root/include/config/kernel.release" "$repo_root/build/wifi-native/kernel.release"
    python3 - "$repo_root/build/wifi-native" <<'PY_MODULE_MANIFEST'
from pathlib import Path
import hashlib,json,sys
p=Path(sys.argv[1]);data=(p/'modules.tar.gz').read_bytes()
(p/'manifest.json').write_text(json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'release':(p/'kernel.release').read_text().strip()},indent=2)+'\n')
PY_MODULE_MANIFEST
fi
if [[ "${A6_INCREMENTAL_BUILD:-0}" == 1 ]]; then
    python3 "$repo_root/scripts/a6-kbuild-cache.py" capture "$linux_root" "$output_root"
fi

dtc_bin="$(command -v dtc || true)"
if [[ -z "$dtc_bin" ]]; then
	make "${make_args[@]}" scripts_dtc
	dtc_bin="$output_root/scripts/dtc/dtc"
fi

"$dtc_bin" -I dts -O dtb -o "$dtb" "$dts"
cat -- "$zimage" "$dtb" > "$combined"

printf 'zImage:  %s (%s bytes)\n' "$zimage" "$(stat -c %s "$zimage")"
printf 'DTB:     %s (%s bytes)\n' "$dtb" "$(stat -c %s "$dtb")"
printf 'combined: %s (%s bytes)\n' "$combined" "$(stat -c %s "$combined")"
file "$zimage" "$dtb" "$combined"
sha256sum "$zimage" "$dtb" "$combined"

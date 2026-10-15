#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Reuse the Stage A platform overlays in a separate output tree. The
# default profile stops before IMG3 packaging; the explicit CPU0-only
# profile packages only with two independent maxcpus=1/DT safeguards.
export A6_SMP_COMPILE_ONLY=1 A6_SMP_LOCAL_TLBI=1 A6_BUILD_JOBS=4
export A6_USB_BUS_POWERED=1 A6_CHARGER_PROOF=1 A6_D1972_POWER_SUPPLY=1 A6_DIRECT_DRM=1
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1
export A6_TOUCH_CLOCK=1 A6_TOUCH_I2C=1 A6_TOUCH_CHECK=1 A6_TOUCH_PWM_CHECK=1 A6_TOUCH_POWER_CHECK=1
export A6_TOUCH_CHECK_KIND=charger-proof
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1
export A6_D1972_TBAT_ADC=1 A6_D1972_POLICY=1
export A6_D1972_STOCK_OFF_CANDIDATE=1 A6_D1972_LOW_BATTERY_CANDIDATE=1
export A6_D1972_BOOT_DEFAULTS=1
export A6_USB_VBUS_BRIDGE=1 A6_USB_WALL_SCREEN=1
export A6_USB_RECONNECT_SCREEN=1 A6_USB_RECONNECT_PHY=1
export A6_USB_RECONNECT_VBUS_LATCH=1 A6_USB_CORE_RESET_TRACE=1
export A6_USB_CORE_STAGE_TRACE=1 A6_USB_VBUS_AUTO_RECOVER=1

bash scripts/build-a6-usb-console.sh
if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
    suffix=smp-cpu0-only
elif [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
    if [[ "${A6_SMP_SCHEDULING:-0}" == 1 ]]; then
        suffix=smp-first-scheduling
    else
        if [[ "${A6_SMP_TIMER_LINE_PROBE:-0}" == 1 ]]; then
            suffix=smp-timer-line-checkpoint
        else
            suffix=smp-bridge-quarantine
        fi
    fi
else
    suffix=smp-compile-only
fi
profile=low-battery-boot-defaults
if [[ "${A6_TOUCH_RAM_ROOT_CANDIDATE:-0}" == 1 ]]; then
    profile="$profile-touch-ram-root"
    if [[ "${A6_TOUCH_FRAME_CAPTURE:-0}" == 1 ]]; then profile="$profile-frames"; fi
    if [[ "${A6_TOUCH_NATIVE_INPUT:-0}" == 1 ]]; then profile="$profile-native"; fi
fi
if [[ "${A6_WIFI_CLOCK_SNAPSHOT:-0}" == 1 ]]; then
    if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
        profile="$profile-wifi-ehci-enum"
    elif [[ "${A6_WIFI_EHCI_CAPS:-0}" == 1 ]]; then
        profile="$profile-wifi-ehci-caps"
    else
        profile="$profile-wifi-clock-snapshot"
    fi
fi
config="build/linux-a6-$profile-$suffix/.config"
rg -q '^# CONFIG_HOTPLUG_CPU is not set$' "$config"
rg -q '^# CONFIG_CPU_IDLE is not set$' "$config"
python3 scripts/a6-smp-secondary-entry.py \
    "build/linux-a6-$profile-$suffix"
python3 scripts/check-a6-smp-local-tlbi.py \
    "build/linux-a6-$profile-$suffix" \
    "build/session-logs/smp-local-tlbi-$suffix"

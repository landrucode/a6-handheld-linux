#!/usr/bin/env bash
# Isolated RAM-only touch report probe with accepted SMP/power protection.
set -euo pipefail
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
export A6_INCREMENTAL_BUILD="${A6_INCREMENTAL_BUILD:-1}"
export A6_TOUCH_RAM_ROOT_CANDIDATE=1 A6_RAM_ROOT=1
export A6_SMP_BRIDGE_QUARANTINE=1 A6_SMP_SCHEDULING=1
export A6_TOUCH_GPIO_CS=1 A6_TOUCH_HBPP=1 A6_TOUCH_FW_UPLOAD=1
export A6_TOUCH_POST_UPLOAD=1 A6_TOUCH_REPORT_PROBE=1 A6_TOUCH_CALIBRATION=1
export A6_TOUCH_CORRECT_EXEC_ADDR=1 A6_TOUCH_E2_RETRY=1
export A6_TOUCH_CLK32_ENABLE=1 A6_TOUCH_E3_INFO=1
export A6_TOUCH_REPORT_METADATA=1
if [[ "${A6_TOUCH_NATIVE_INPUT:-0}" == 1 ]]; then export A6_TOUCH_FRAME_CAPTURE=1; fi
bash scripts/build-a6-smp-compile-only.sh
profile=low-battery-boot-defaults-touch-ram-root
if [[ "${A6_TOUCH_FRAME_CAPTURE:-0}" == 1 ]]; then profile="$profile-frames"; fi
if [[ "${A6_TOUCH_NATIVE_INPUT:-0}" == 1 ]]; then profile="$profile-native"; fi
if [[ "${A6_WIFI_CLOCK_SNAPSHOT:-0}" == 1 ]]; then
    if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
        profile="$profile-wifi-ehci-enum"
    elif [[ "${A6_WIFI_EHCI_CAPS:-0}" == 1 ]]; then
        profile="$profile-wifi-ehci-caps"
    else
        profile="$profile-wifi-clock-snapshot"
    fi
fi
sha256sum "build/arm/a6-linux-$profile-smp-first-scheduling.img3"

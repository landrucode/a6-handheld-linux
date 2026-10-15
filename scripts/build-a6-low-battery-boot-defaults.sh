#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1
export A6_D1972_TBAT_ADC=1 A6_D1972_POLICY=1
export A6_D1972_STOCK_OFF_CANDIDATE=1 A6_D1972_LOW_BATTERY_CANDIDATE=1
export A6_D1972_BOOT_DEFAULTS=1
export A6_USB_VBUS_BRIDGE=1 A6_USB_WALL_SCREEN=1
export A6_USB_RECONNECT_SCREEN=1 A6_USB_RECONNECT_PHY=1
export A6_USB_RECONNECT_VBUS_LATCH=1 A6_USB_CORE_RESET_TRACE=1
export A6_USB_CORE_STAGE_TRACE=1 A6_USB_VBUS_AUTO_RECOVER=1
bash scripts/build-a6-charger-usb-power.sh
sha256sum build/arm/a6-linux-low-battery-boot-defaults.img3

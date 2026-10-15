#!/usr/bin/env bash
# Combined repeatable passive Wi-Fi and compressed RAM-root diagnostic.
set -euo pipefail
cd "$(dirname "$0")/.."
export A6_TOUCH_NATIVE_INPUT=1 A6_WIFI_CLOCK_SNAPSHOT=1 A6_WIFI_EHCI_ENUM=1
export A6_WIFI_USB_IDENTITY=1 A6_WIFI_USB_OTP=1 A6_WIFI_USB_DOWNLOAD=1
export A6_WIFI_USB_EXECUTE=1 A6_WIFI_USB_RUNTIME=1 A6_WIFI_USB_RX=1 A6_WIFI_USB_SCAN=1
export A6_WIFI_USB_PREFLIGHT=0 A6_WIFI_USB_COUNTRY=0 A6_WIFI_USB_LOOPBACK=0
export A6_RAM_ROOT_XZ=1 A6_RAM_ROOT_COMPONENTS=1
export KCFLAGS=-Oz
export KBUILD_BUILD_TIMESTAMP='Fri Oct 2 22:00:00 UTC 2026' KBUILD_BUILD_VERSION=1
bash scripts/build-a6-touch-ram-root-smp.sh
destination=build/arm/a6-wifi-combined.img3
if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then destination=build/arm/a6-wifi-brcmfmac.img3; fi
cp build/arm/a6-linux-low-battery-boot-defaults-touch-ram-root-frames-native-wifi-ehci-enum-smp-first-scheduling.img3 "$destination"

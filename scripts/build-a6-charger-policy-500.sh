#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1
export A6_D1972_TBAT_ADC=1 A6_D1972_POLICY=1
bash scripts/build-a6-charger-usb-power.sh
if [[ "${A6_USB_RECONNECT_SCREEN:-0}" != 1 ]]; then
    sha256sum build/arm/a6-linux-charger-policy-500.img3
fi

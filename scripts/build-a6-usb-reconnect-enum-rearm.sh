#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_USB_RECONNECT_SCREEN=1
export A6_USB_RECONNECT_PHY=1
export A6_USB_RECONNECT_ENUM_REARM=1
bash scripts/build-a6-charger-policy-500.sh
sha256sum build/arm/a6-linux-usb-reconnect-enum-rearm.img3

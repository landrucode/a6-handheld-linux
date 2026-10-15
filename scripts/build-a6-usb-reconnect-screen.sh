#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_USB_RECONNECT_SCREEN=1
bash scripts/build-a6-charger-policy-500.sh
sha256sum build/arm/a6-linux-usb-reconnect-screen.img3

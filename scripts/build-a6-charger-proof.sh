#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_CHARGER_PROOF=1 A6_DIRECT_DRM=1
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1
export A6_TOUCH_CLOCK=1 A6_TOUCH_I2C=1 A6_TOUCH_CHECK=1 A6_TOUCH_PWM_CHECK=1 A6_TOUCH_POWER_CHECK=1
export A6_TOUCH_CHECK_KIND=charger-proof
bash scripts/build-a6-usb-console.sh
python3 scripts/verify-a6-charger-proof.py
sha256sum build/arm/a6-linux-charger-proof.img3

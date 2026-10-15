#!/usr/bin/env bash
# Fixed, volatile N42 firmware upload candidate; build only, never auto-run.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
export A6_USB_BUS_POWERED=1 A6_CHARGER_PROOF=1 A6_D1972_POWER_SUPPLY=1 A6_DIRECT_DRM=1
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1
export A6_BATTERY_HDQ_READ=1 A6_HDQ_LINE_OBSERVER=1 A6_HDQ_PHASE_OBSERVER=1
export A6_HDQ_REALTIME_US=1 A6_HDQ_ECHO_GUARD=1 A6_POWER_HDQ_ECHO_GUARD=1
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1
export A6_TOUCH_CLOCK=1 A6_TOUCH_I2C=1 A6_TOUCH_CHECK=1 A6_TOUCH_PWM_CHECK=1 A6_TOUCH_POWER_CHECK=1
export A6_TOUCH_GPIO_CS=1 A6_TOUCH_HBPP=1 A6_TOUCH_FW_UPLOAD=1
export A6_TOUCH_CHECK_KIND=charger-proof A6_BUILD_JOBS=4
bash scripts/build-a6-usb-console.sh
sha256sum build/arm/a6-linux-touch-fw-n42.img3

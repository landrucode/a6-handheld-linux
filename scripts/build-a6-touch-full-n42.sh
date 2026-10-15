#!/usr/bin/env bash
# RAM-only N42 factory calibration, firmware, corrected execute and report probe.
set -euo pipefail
# The linked kernel and IMG3 contain this phone's private factory calibration.
umask 077
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
export A6_USB_BUS_POWERED=1 A6_CHARGER_PROOF=1 A6_D1972_POWER_SUPPLY=1 A6_DIRECT_DRM=1
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1
export A6_BATTERY_HDQ_READ=1 A6_HDQ_LINE_OBSERVER=1 A6_HDQ_PHASE_OBSERVER=1
export A6_HDQ_REALTIME_US=1 A6_HDQ_ECHO_GUARD=1 A6_POWER_HDQ_ECHO_GUARD=1
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1
export A6_TOUCH_CLOCK=1 A6_TOUCH_I2C=1 A6_TOUCH_CHECK=1 A6_TOUCH_PWM_CHECK=1 A6_TOUCH_POWER_CHECK=1
export A6_TOUCH_GPIO_CS=1 A6_TOUCH_HBPP=1 A6_TOUCH_FW_UPLOAD=1 A6_TOUCH_POST_UPLOAD=1
export A6_TOUCH_REPORT_PROBE=1 A6_TOUCH_CALIBRATION=1 A6_TOUCH_CORRECT_EXEC_ADDR=1
export A6_TOUCH_CHECK_KIND=charger-proof A6_BUILD_JOBS=4
bash scripts/build-a6-usb-console.sh
kind=touch-full-n42
if [[ "${A6_TOUCH_E2_RETRY:-0}" == 1 ]]; then kind=touch-retry-n42; fi
if [[ "${A6_TOUCH_CLK32_ENABLE:-0}" == 1 ]]; then kind=touch-clk32-n42; fi
if [[ "${A6_TOUCH_E3_INFO:-0}" == 1 ]]; then kind=touch-e3-info-n42; fi
if [[ "${A6_CHARGER_ACTIVE_TRIAL:-0}" == 1 ]]; then kind=touch-charge-trial-n42; fi
chmod 700 "build/linux-a6-$kind"
chmod 600 "build/arm/a6-linux-$kind.img3" "build/arm/a6-linux-$kind.raw" \
    "build/arm/a6-n42ap-$kind.dtb" \
    "build/arm/a6-n42ap-$kind-zImage-with-dtb"
sha256sum "build/arm/a6-linux-$kind.img3"

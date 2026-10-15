#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1
export A6_BATTERY_HDQ_READ=1 A6_HDQ_LINE_OBSERVER=1 A6_HDQ_PHASE_OBSERVER=1
export A6_HDQ_REALTIME_US=1 A6_POWER_HDQ_TIMED=1
bash scripts/build-a6-charger-usb-power.sh
python3 scripts/verify-a6-charger-vbus-adc.py charger-vbat-hdq-timed
python3 scripts/verify-a6-charger-vbat-monitor.py charger-vbat-hdq-timed
python3 scripts/verify-a6-charger-vbat-hdq-phase.py charger-vbat-hdq-timed
sha256sum build/arm/a6-linux-charger-vbat-hdq-timed.img3

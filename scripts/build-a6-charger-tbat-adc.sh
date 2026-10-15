#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_D1972_VBUS_ADC=1 A6_D1972_VBAT_ADC=1 A6_D1972_VBAT_MONITOR=1 A6_D1972_TBAT_ADC=1
bash scripts/build-a6-charger-usb-power.sh
python3 - <<'PY'
from pathlib import Path
image = Path('build/linux-a6-charger-tbat-adc/vmlinux').read_bytes()
assert image.count(b'A6_D1972_TBAT_RAW_V1') == 1
assert image.count(b'sample-tbat-once-and-restore') == 1
print('PASS: raw TBAT probe linked once')
PY
sha256sum build/arm/a6-linux-charger-tbat-adc.img3

#!/usr/bin/env bash
# Correct external GPIO chip-select; preserve tested power/PWM scope.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
python3 - <<'CHECK'
from pathlib import Path
import hashlib
p=Path('build/arm/a6-linux-touch-pmu-read.img3')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='815359813f0173c40f11ebd5db5c60e962a7babac31d262cdc12ab7e1ad7f57c'
p=Path('build/arm/a6-linux-touch-power-check.img3')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='75a446204f000a18b12fdf90821d5401fd223edd0d64147046b7f1ef8f675fb2'
p=Path('build/arm/a6-linux-touch-pwm-steady.img3')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='73cdf8c214dc4062e8494feb1a6867333419ae0575773767783d05238606b929'
CHECK
python3 scripts/verify-a6-stock-touch-i2c.py > build/touch-i2c-stock-verification.json
python3 scripts/test-a6-touch-i2c.py
python3 scripts/verify-a6-stock-touch-pmu.py > build/touch-pmu-stock-verification.json
python3 scripts/verify-a6-stock-touch-power.py > build/touch-power-stock-verification.json
python3 scripts/verify-a6-stock-touch-pwm.py > build/touch-pwm-stock-verification.json
python3 scripts/verify-a6-stock-touch-check.py
python3 scripts/verify-a6-stock-touch-gpio-cs.py > build/touch-gpio-cs-stock-verification.json
python3 scripts/test-a6-touch-gpio-cs.py
python3 scripts/test-a6-clock-capture.py --cpu
export A6_TOUCH_PMU_READ=0 A6_TOUCH_I2C=1 A6_TOUCH_CLOCK=1 A6_TOUCH_CHECK=1 A6_TOUCH_PWM_CHECK=1
export A6_TOUCH_POWER_CHECK=1 A6_TOUCH_GPIO_CS=1 A6_TOUCH_CHECK_KIND=touch-gpio-cs
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1 A6_DIRECT_DRM=1
bash scripts/build-a6-usb-console.sh
python3 scripts/verify-a6-touch-transport.py touch-gpio-cs > build/touch-gpio-cs-verification.json
python3 - <<'MANIFEST'
from pathlib import Path
import hashlib,json
paths=['build/arm/a6-linux-touch-gpio-cs.img3','build/arm/a6-linux-touch-gpio-cs.raw',
 'build/arm/a6-n42ap-touch-gpio-cs.dtb','build/linux-a6-touch-gpio-cs/arch/arm/boot/zImage',
 'kernel/platform/a6-touch-transport.inc','kernel/platform/a6-touch-i2c.inc','kernel/platform/a6-touch-power-check.inc','kernel/platform/a6-touch-check.inc',
 'kernel/platform/a6-touch-clock.inc','kernel/platform/a6-touch-pwm-check.inc',
 'boot/arm/capture-memory.c','boot/arm/capture-clock.inc']
report={p:{'bytes':Path(p).stat().st_size,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in paths}
Path('build/arm/a6-touch-gpio-cs-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
MANIFEST

#!/usr/bin/env bash
# Fixed common-page PMU reads; no PMU data/bank/rail writes.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
python3 - <<'CHECK'
from pathlib import Path
import hashlib
p=Path('build/arm/a6-linux-touch-i2c.img3')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='2c79aab6d3dad553d800ba94b161b67e2d4bdd0de7dd36c2ae11715aea4f30ba'
CHECK
python3 scripts/verify-a6-stock-touch-i2c.py > build/touch-i2c-stock-verification.json
python3 scripts/test-a6-touch-i2c.py
python3 scripts/verify-a6-stock-touch-pmu.py > build/touch-pmu-stock-verification.json
python3 scripts/test-a6-touch-pmu-read.py
python3 scripts/test-a6-clock-capture.py --cpu
export A6_TOUCH_PMU_READ=1 A6_TOUCH_I2C=1 A6_TOUCH_CLOCK=0 A6_TOUCH_CHECK=0 A6_TOUCH_PWM_CHECK=0
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1 A6_DIRECT_DRM=1
bash scripts/build-a6-usb-console.sh
python3 scripts/verify-a6-touch-transport.py touch-pmu-read > build/touch-pmu-read-verification.json
python3 - <<'MANIFEST'
from pathlib import Path
import hashlib,json
paths=['build/arm/a6-linux-touch-pmu-read.img3','build/arm/a6-linux-touch-pmu-read.raw',
 'build/arm/a6-n42ap-touch-pmu-read.dtb','build/linux-a6-touch-pmu-read/arch/arm/boot/zImage',
 'kernel/platform/a6-touch-transport.inc','kernel/platform/a6-touch-i2c.inc','kernel/platform/a6-touch-pmu-read.inc',
 'boot/arm/capture-memory.c','boot/arm/capture-clock.inc']
report={p:{'bytes':Path(p).stat().st_size,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in paths}
Path('build/arm/a6-touch-pmu-read-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
MANIFEST

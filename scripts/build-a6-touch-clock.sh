#!/usr/bin/env bash
# Capture live clocks and observe PWM channel2; no waveform or rail writes.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
python3 - <<'PY'
from pathlib import Path
import hashlib
pins={
 'build/arm/a6-linux-touch-check-start.img3':'0b9cbf986b28f53d844335a273acb46bd26867a0b91f0713f1e0e2a66f738530',
 'build/touch-research/ios10-touch-dependencies/com.apple.driver.AppleS5L8920XPWM.macho':'b715106761c7bb3608bc7d91e2c3eac2213025507bffdda02ee27cead3afc105',
 'build/arm/a6-linux-touch-capture.img3':'b1db56f6c53a057dd63e88ee4279887ba43803decdb90b64c82254cc678189ee',
 'build/arm/a6-n42ap-arch-direct-drm-ram768.dtb':'c0e4bf6476ba711798a0586bce7277febf7591c0bbeb40088b12282090a72a88',
 '.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw':'a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef',
}
for path,digest in pins.items():
    p=Path(path)
    assert p.is_file(),path
    assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,path
tree=Path('.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw').read_bytes()
clock=bytes.fromhex('0000001b00000000000000003a00000000000000000000000000000053504931000000000000000000000000')
assert tree.count(clock)==1, 'SPI1 logical-ID/register-index mapping changed'
# Match properties on the touchscreen node, not identical pin descriptors
# belonging to other devices in the flat byte stream.
import json, subprocess
inventory=json.loads(subprocess.check_output([
    'python3', 'scripts/inspect-a6-touch-tree.py',
    '.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw']))
node=[n for n in inventory['nodes']
      if n['path']=='/device-tree/arm-io/spi1/multi-touch']
assert len(node)==1, 'expected exactly one SPI1 touchscreen node'
props=node[0]['properties']
assert props['function-enable_cs']['hex']=='0000000f4f4950470106000001010000'
assert props['function-reset']['hex']=='0000000f4f495047071c000001000100' 
pwm_nodes={n['path']:n['properties'] for n in inventory['nodes']}
armio=pwm_nodes['/device-tree/arm-io']
pwm=pwm_nodes['/device-tree/arm-io/pwm']
grape=pwm_nodes['/device-tree/arm-io/pwm/grape-clk']
assert armio['ranges']['le32']==[0,0x30000000,0x10000000]
assert pwm['reg']['le32']==[0x03500000,0x1000]
assert pwm['clock-gates']['le32']==[0x2c]
assert grape['reg']['le32']==[2] and grape['default-hz']['le32']==[32768]
pwm_clock=bytes.fromhex('0000002c00000000000000004900000000000000000000000000000050574d00000000000000000000000000')
assert tree.count(pwm_clock)==1
pwm_source=Path('kernel/platform/a6-touch-clock.inc').read_text()
assert '#define A6_TOUCH_PWM_BASE 0x33500000' in pwm_source
assert '#define A6_TOUCH_PWM_GATE 0x124' in pwm_source
source=Path('kernel/platform/a6-touch-transport.inc').read_text()
for name,value in {'A6_TOUCH_GATE':0x3a*4,
                   'A6_TOUCH_CS':((0x0601 >> 8)*8+(0x0601 & 7))*4,
                   'A6_TOUCH_RESET':((0x1c07 >> 8)*8+(0x1c07 & 7))*4}.items():
    import re
    found=re.search(r'^#define '+name+r'\s+(0x[0-9a-f]+)',source,re.M)
    assert found and int(found[1],16)==value, name
print('PASS preserved checked capture fallback and768MiB DT')
print('PASS pinned stock SPI1 gate and GPIO pin mappings')
PY
python3 scripts/test-a6-clock-capture.py
python3 scripts/test-a6-touch-clock.py
export A6_TOUCH_CLOCK=1 A6_TOUCH_CHECK=0 A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_DIRECT_DRM=1
bash scripts/build-a6-usb-console.sh
cmp build/arm/a6-n42ap-touch-clock.dtb build/arm/a6-n42ap-arch-direct-drm-ram768.dtb
python3 scripts/verify-a6-touch-transport.py touch-clock > build/touch-clock-verification.json
python3 - <<'PY'
from pathlib import Path
import hashlib,json
paths=['build/arm/a6-linux-touch-clock.img3',
       'build/arm/a6-linux-touch-clock.raw',
       'build/arm/a6-n42ap-touch-clock.dtb',
       'build/linux-a6-touch-clock/arch/arm/boot/zImage',
       'kernel/platform/a6-touch-transport.inc', 'kernel/platform/a6-touch-clock.inc',
       'boot/arm/capture-memory.c', 'boot/arm/capture-clock.inc']
report={p:{'bytes':Path(p).stat().st_size,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in paths}
Path('build/arm/a6-touch-clock-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
PY

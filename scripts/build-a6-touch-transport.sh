#!/usr/bin/env bash
# Dedicated fixed-register observer; preserve all previous boot artifacts.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
python3 - <<'PY'
from pathlib import Path
import hashlib
pins={
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
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=1 A6_DIRECT_DRM=1
bash scripts/build-a6-usb-console.sh
cmp build/arm/a6-n42ap-touch-transport.dtb build/arm/a6-n42ap-arch-direct-drm-ram768.dtb
python3 scripts/verify-a6-touch-transport.py > build/touch-transport-verification.json
python3 - <<'PY'
from pathlib import Path
import hashlib,json
paths=['build/arm/a6-linux-touch-transport.img3',
       'build/arm/a6-linux-touch-transport.raw',
       'build/arm/a6-n42ap-touch-transport.dtb',
       'build/linux-a6-touch-transport/arch/arm/boot/zImage',
       'kernel/platform/a6-touch-transport.inc']
report={p:{'bytes':Path(p).stat().st_size,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in paths}
Path('build/arm/a6-touch-transport-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
PY

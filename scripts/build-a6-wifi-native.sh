#!/usr/bin/env bash
# Native brcmfmac modules + retained N42 HSIC host, RAM only.
set -euo pipefail
cd "$(dirname "$0")/.."
export A6_WIFI_NATIVE=1
export A6_WIFI_BOOT_DEFAULTS="${A6_WIFI_BOOT_DEFAULTS:-1}"
if [[ "$A6_WIFI_BOOT_DEFAULTS" == 1 ]]; then python3 scripts/prepare-a6-boot-assets.py; fi
bash scripts/build-a6-wifi-combined.sh
python3 scripts/prepare-a6-wifi-tools.py
tar -C build/wifi-native -czf build/wifi-native/modules.tar.gz modules tools
python3 - <<'PY'
from pathlib import Path
import hashlib,json,re,subprocess,os
p=Path('build/wifi-native');a=p/'modules.tar.gz'
modules={x.stem.replace('-','_'):x for x in (p/'modules').glob('*.ko')}
order=[];visiting=set()
def add(name):
 if name in order:return
 if name in visiting:raise RuntimeError('Module dependency cycle')
 visiting.add(name)
 if name not in modules:raise RuntimeError('Missing firewall module dependency: '+name)
 data=subprocess.check_output(['llvm-readelf','-p','.modinfo',str(modules[name])],text=True)
 match=re.search(r'\bdepends=([^\s]*)',data)
 for dep in (match.group(1).split(',') if match else []):
  if dep:add(dep.replace('-','_'))
 visiting.remove(name);order.append(name)
for name in ('nf_tables','nf_conntrack','nft_ct','udp_diag'):add(name)
(p/'firewall-modules.json').write_text(json.dumps([modules[n].stem for n in order],indent=2)+'\n')
(p/'manifest.json').write_text(json.dumps({'sha256':hashlib.sha256(a.read_bytes()).hexdigest(),'bytes':a.stat().st_size,'release':(p/'kernel.release').read_text().strip(),'image_sha256':hashlib.sha256(Path('build/arm/a6-wifi-brcmfmac.img3').read_bytes()).hexdigest(),'boot_cpus':int(os.environ.get('A6_WIFI_BOOT_CPUS','2')),'hardening':os.environ.get('A6_WIFI_HARDENING','1')=='1','boot_defaults':os.environ.get('A6_WIFI_BOOT_DEFAULTS')=='1'},indent=2)+'\n')
PY
if [[ "$A6_WIFI_BOOT_DEFAULTS" == 1 ]]; then
    signed="build/signed-updates/boot-$(date -u +%s)"
    python3 scripts/sign-a6-update.py --output "$signed"
    python3 - "$signed" <<'PY_SIGNED'
import json,sys
from pathlib import Path
Path('build/wifi-native/signed-update.json').write_text(json.dumps({'directory':sys.argv[1]})+'\n')
PY_SIGNED
fi

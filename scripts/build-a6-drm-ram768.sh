#!/usr/bin/env bash
# Repack the proven direct-DRM kernel with a bounded 768MiB memory DT.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_ZIMAGE="$repo_root/build/linux-a6-arch-direct-drm/arch/arm/boot/zImage"
python3 - <<'PY'
import hashlib, importlib.util, struct, subprocess
from pathlib import Path
pins = {
 'build/linux-a6-arch-direct-drm/arch/arm/boot/zImage': 'd02081e7cf1a3a790d2bd5fd37aff52f87b1fd14f8c2ca8b5137911156e09ae4',
 'build/arm/a6-n42ap-arch-direct-drm.dtb': '26c9206acbbc764415077255b94773abc4a17c847eea4c1c6c68d04cd8bf15be',
 'build/arm/a6-linux-arch-direct-drm.raw': '1254a888b2beb800139467d634e4f6a9ed32f99778be0393310a8ba0f37a0c24',
 'build/session-logs/a6-memory-v17.bin': 'e5ea0a481aebaed6c096040e92d6dc4c2157b7b9e4531dfd63faa19c00055348',
}
for name, digest in pins.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
spec=importlib.util.spec_from_file_location('capture_decoder','scripts/decode-a6-memory-capture.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
report=module.decode(Path('build/session-logs/a6-memory-v17.bin').read_bytes())
assert report['complete_untruncated'] and report['reported_ram_bytes']==0x3f7aa000
assert int(report['framebuffer_base'],16)>=0xb0000000
for record in report['records']:
    for pair in record.get('candidate_address_size_pairs',[]):
        if pair['size']:
            assert pair['within_reported_ram'] and int(pair['end_exclusive'],16)<=0x88000000
# Pinned ARM 3G/1G layout: default 240MiB vmalloc plus8MiB gap leaves768MiB.
assert 0xff800000 - 240*1024*1024 - 8*1024*1024 - 0xc0000000 == 0x30000000
config=Path('build/linux-a6-arch-direct-drm/.config').read_text()
assert 'CONFIG_VMSPLIT_3G=y' in config and '# CONFIG_HIGHMEM is not set' in config
original=Path('build/arm/a6-n42ap-arch-direct-drm.dtb').read_bytes()
needle=struct.pack('>II',0x80000000,0x20000000)
assert original.count(needle)==1
changed=original.replace(needle,struct.pack('>II',0x80000000,0x30000000))
assert len(changed)==len(original) and sum(a!=b for a,b in zip(original,changed))==1
output=Path('build/arm/a6-n42ap-arch-direct-drm-ram768.dtb');output.write_bytes(changed)
dts=subprocess.check_output(['build/linux-a6-arch-direct-drm/scripts/dtc/dtc',
    '-I','dtb','-O','dts',str(output)],text=True)
assert 'reg = <0x80000000 0x30000000>;' in dts
assert 'reg = <0x83fff000 0x1000>;' in dts and 'no-map;' in dts
output.with_suffix('.dts').write_text(dts)
print('PASS pinned kernel/capture; one DT byte512->768MiB; scratch preserved')
PY
export A6_DTB="$repo_root/build/arm/a6-n42ap-arch-direct-drm-ram768.dtb"
export A6_MEMORY_CAPTURE=1 A6_USB_NETWORK=1 A6_USB_SHELL=1
export A6_PAYLOAD="$repo_root/build/arm/a6-n42ap-arch-direct-drm-ram768-zImage-with-dtb"
export A6_KERNELCACHE_RAW="$repo_root/build/arm/a6-linux-arch-direct-drm-ram768.raw"
export A6_KERNELCACHE_IMG3="$repo_root/build/arm/a6-linux-arch-direct-drm-ram768.img3"
export A6_KERNELCACHE_ROUNDTRIP="$repo_root/build/arm/a6-linux-arch-direct-drm-ram768.roundtrip.raw"
bash scripts/build-a6-kernelcache.sh
python3 - <<'PY'
from pathlib import Path
import hashlib
old=Path('build/arm/a6-linux-arch-direct-drm.raw').read_bytes()
new=Path('build/arm/a6-linux-arch-direct-drm-ram768.raw').read_bytes()
assert len(old)==len(new)
changes=[(i,a,b) for i,(a,b) in enumerate(zip(old,new)) if a!=b]
assert len(changes)==1 and changes[0][1:]==(0x20,0x30),changes[:20]
print('PASS complete raw image differs only at RAM-size byte:',changes)
p=Path('build/arm/a6-linux-arch-direct-drm-ram768.img3')
print(hashlib.sha256(p.read_bytes()).hexdigest(),p)
PY

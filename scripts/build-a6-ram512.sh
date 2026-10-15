#!/usr/bin/env bash
# Repack the checked memory-capture kernel with the reviewed 512 MiB DT and version17 handoff.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_ZIMAGE="$repo_root/build/linux-a6-arch-memory-capture/arch/arm/boot/zImage"
export A6_DTB="$repo_root/build/arm/a6-n42ap-arch-memory-capture.dtb"
python3 - "$A6_ZIMAGE" "$A6_DTB" <<'PY'
import hashlib,sys
from pathlib import Path
for p,h in zip(sys.argv[1:],[
 '74a5e45fcee2c46cacae6ad74ad24d13c502f373072b3f84af37e804f6290d0c',
 '2dc6e11eb70b10df655ca49124b27921f338b051769d6b15a6341ae97e2bece5']):
 assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h, p
print('PASS unchanged checked kernel and original DT')
# This candidate is tied to the reviewed, complete hardware capture.
import importlib.util, struct, subprocess
capture=Path('build/session-logs/a6-memory-v17.bin').read_bytes()
assert hashlib.sha256(capture).hexdigest()=='e5ea0a481aebaed6c096040e92d6dc4c2157b7b9e4531dfd63faa19c00055348'
spec=importlib.util.spec_from_file_location('capture_decoder','scripts/decode-a6-memory-capture.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
report=module.decode(capture)
assert report['complete_untruncated'] and report['reported_ram_bytes']==0x3f7aa000
assert int(report['framebuffer_base'],16)>=0xa0000000
for record in report['records']:
 for pair in record.get('candidate_address_size_pairs',[]):
  if pair['size']:
   assert pair['within_reported_ram'] and int(pair['end_exclusive'],16)<=0x88000000
# Preserve the exact DT layout: the unique memory reg changes size only.
original=Path(sys.argv[2]).read_bytes()
needle=struct.pack('>II',0x80000000,0x08000000)
assert original.count(needle)==1
changed=original.replace(needle,struct.pack('>II',0x80000000,0x20000000))
assert sum(a!=b for a,b in zip(original,changed))==1
output=Path('build/arm/a6-n42ap-arch-ram512.dtb');output.write_bytes(changed)
dtc='build/linux-a6-arch-memory-capture/scripts/dtc/dtc'
dts=subprocess.check_output([dtc,'-I','dtb','-O','dts',str(output)],text=True)
assert 'reg = <0x80000000 0x20000000>;' in dts
assert 'reg = <0x83fff000 0x1000>;' in dts and 'no-map;' in dts
output.with_suffix('.dts').write_text(dts)
print('PASS reviewed capture; DT changes only RAM128->512 MiB; scratch preserved')
PY
export A6_DTB="$repo_root/build/arm/a6-n42ap-arch-ram512.dtb"
export A6_MEMORY_CAPTURE=1 A6_USB_NETWORK=1 A6_USB_SHELL=1
export A6_PAYLOAD="$repo_root/build/arm/a6-n42ap-arch-ram512-zImage-with-dtb"
export A6_KERNELCACHE_RAW="$repo_root/build/arm/a6-linux-arch-ram512.raw"
export A6_KERNELCACHE_IMG3="$repo_root/build/arm/a6-linux-arch-ram512.img3"
export A6_KERNELCACHE_ROUNDTRIP="$repo_root/build/arm/a6-linux-arch-ram512.roundtrip.raw"
bash scripts/build-a6-kernelcache.sh

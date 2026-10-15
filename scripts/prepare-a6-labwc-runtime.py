#!/usr/bin/env python3
"""Stage a signed, public ARM Pixman compositor comparison and GTK image runtime."""
import hashlib,json,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
stage=ROOT/'build/labwc';stage.mkdir(exist_ok=True)
runtime=stage/'runtime';runtime.mkdir(exist_ok=True)
spec=json.loads((ROOT/'rootfs/arch-labwc-packages.json').read_text())
aqua=json.loads((ROOT/'rootfs/arch-aquamarine-build-packages.json').read_text())
def verified(package,metadata,mirror,signer,cache):
 p=cache/package
 for suffix in ('','.sig'):
  target=Path(str(p)+suffix)
  cached=ROOT/'build/arch-bootstrap/downloads'/(package+suffix)
  if not target.exists() and cached.is_file():shutil.copyfile(cached,target)
  if not target.exists():
   partial=Path(str(target)+'.partial')
   subprocess.run(['curl','-fsSL','--max-time','120',mirror+package+suffix,'-o',str(partial)],check=True);partial.replace(target)
 if hashlib.sha256(p.read_bytes()).hexdigest()!=metadata['sha256']:raise ValueError('Package changed: '+package)
 r=subprocess.run(['gpg','--homedir',str(ROOT/'build/arch-bootstrap/gnupg'),'--batch','--status-fd','1','--verify',str(p)+'.sig',str(p)],capture_output=True,text=True,check=True)
 if '[GNUPG:] VALIDSIG '+signer+' ' not in r.stdout:raise ValueError('Wrong package signer')
 return p
for name,metadata in spec['packages'].items():
 p=verified(name,metadata,spec['mirror'],spec['signing_fingerprint'],stage)
 with tarfile.open(p) as t:
  for member in t:
   if member.name.startswith('usr/'):
    t.extract(member,runtime,filter='data')
# Four libraries missing from the actual desktop root, verified from pinned packages.
for soname,package in spec['additional_libraries'].items():
 metadata=aqua['packages'][package];p=verified(metadata['filename'],metadata,aqua['mirror']+metadata['repo']+'/',aqua['signing_fingerprint'],ROOT/'build/arch-bootstrap/downloads')
 with tarfile.open(p) as t:
  member=t.getmember('usr/lib/'+soname)
  while member.issym():member=t.getmember('usr/lib/'+member.linkname)
  dest=runtime/'usr/lib'/soname;dest.write_bytes(t.extractfile(member).read());dest.chmod(0o755)
# gdk-pixbuf2 uses external glycin loaders; ELF-only trimming misses these.
metadata=aqua['packages']['glycin'];p=verified(metadata['filename'],metadata,aqua['mirror']+metadata['repo']+'/',aqua['signing_fingerprint'],ROOT/'build/arch-bootstrap/downloads')
with tarfile.open(p) as t:
 for name in ('usr/lib/glycin-loaders/2+/glycin-image-rs','usr/share/glycin-loaders/2+/conf.d/glycin-image-rs.conf'):
  t.extract(name,runtime,filter='data')
subprocess.run(['update-mime-database',str(runtime/'usr/share/mime')],check=True,capture_output=True)
xml=stage/'foreign-toplevel.xml'
if not xml.exists():subprocess.run(['curl','-fsSL','https://raw.githubusercontent.com/swaywm/wlr-protocols/master/unstable/wlr-foreign-toplevel-management-unstable-v1.xml','-o',str(xml)],check=True)
if hashlib.sha256(xml.read_bytes()).hexdigest()!=spec['foreign_protocol_sha256']:raise ValueError('Foreign-toplevel protocol changed')
for p in runtime.rglob('*'):
 if not p.is_symlink():p.chmod(0o755 if p.is_dir() or p.stat().st_mode&0o111 else 0o644)
print('Signed labwc/Pixman and GTK image runtime prepared')

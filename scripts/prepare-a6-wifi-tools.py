#!/usr/bin/env python3
"""Prepare signed ARM iw/libnl/regdb in build/, without phone operations."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,tarfile
ROOT=Path(__file__).resolve().parents[1]
def main():
 archive_root=ROOT/'build/arch-bootstrap';cache=archive_root/'downloads'
 mirror=json.loads((ROOT/'rootfs/arch-tools-packages.json').read_text())['mirror']
 extra_index=ROOT/'build/wifi-native/extra-current.db'
 extra_index.parent.mkdir(parents=True,exist_ok=True)
 if not extra_index.exists():
  subprocess.run(['curl','-fLsS','--max-time','60',mirror+'extra/extra.db','-o',str(extra_index)],check=True)
 wanted={'iw','libnl','wireless-regdb','wpa_supplicant','openssl','dbus','pcsclite','nftables','libmnl','libnftnl','iproute2','socat','libbpf','libelf','jansson','gmp'}
 selected={}
 for repo in ('core','extra'):
  with tarfile.open(extra_index if repo=='extra' else cache/(repo+'.db')) as db:
   for member in db:
    if not member.name.endswith('/desc'):continue
    blocks=db.extractfile(member).read().decode().split('\n\n')
    fields={b.splitlines()[0].strip('%'):b.splitlines()[1:] for b in blocks if b.strip()}
    name=fields.get('NAME',[''])[0]
    if name in wanted:
     selected[name]={'repo':repo,'filename':fields['FILENAME'][0],'sha256':fields['SHA256SUM'][0]}
 if set(selected)!=wanted:raise RuntimeError('ARM package index missing tools: '+str(sorted(wanted-set(selected))))
 output=ROOT/'build/wifi-native';runtime=output/'tools';runtime.mkdir(parents=True,exist_ok=True)
 for name,spec in selected.items():
  p=cache/spec['filename']
  for suffix in ('','.sig'):
   dest=Path(str(p)+suffix)
   if not dest.exists():
    partial=Path(str(dest)+'.part')
    subprocess.run(['curl','-fLsS','--max-time','60',mirror+spec['repo']+'/'+spec['filename']+suffix,'-o',str(partial)],check=True)
    partial.replace(dest)
  if hashlib.sha256(p.read_bytes()).hexdigest()!=spec['sha256']:raise RuntimeError('Package checksum mismatch: '+name)
  verified=subprocess.run(['gpg','--homedir',str(archive_root/'gnupg'),'--batch','--status-fd','1','--verify',str(p)+'.sig',str(p)],capture_output=True,text=True,check=True)
  if '[GNUPG:] VALIDSIG ' not in verified.stdout:raise RuntimeError('Package signature absent: '+name)
  with tarfile.open(p) as t:t.extractall(runtime,filter='data')
 # Use the already-pinned desktop libc/loader, avoiding a full root upload.
 desktop=output/'desktop-libs'
 subprocess.run([str(ROOT/'.deps/squashfs-tools-4.7.2/squashfs-tools/unsquashfs'),'-f','-d',str(desktop),str(archive_root/'arch-hyprland-user-desktop.squashfs'),'graphics-runtime/usr/lib'],check=True,stdout=subprocess.DEVNULL)
 libs=runtime/'usr/lib';seen=set();queue=[runtime/'usr/bin'/n for n in ('iw','wpa_supplicant','wpa_cli','nft','ss','ip','socat','openssl')]
 # Resolve actual ELF dependencies; copied libraries are the pinned desktop
 # versions unless supplied by the signed Wi-Fi packages above.
 while queue:
  obj=queue.pop()
  if obj in seen:continue
  seen.add(obj)
  if not obj.is_file():raise RuntimeError('Missing Wi-Fi tool dependency: '+obj.name)
  dynamic=subprocess.check_output(['llvm-readelf','-d',str(obj)],text=True)
  for name in re.findall(r'Shared library: \[(.*?)\]',dynamic):
   dest=libs/name
   if not dest.exists():
    src=desktop/'graphics-runtime/usr/lib'/name
    if not src.exists():raise RuntimeError('Missing desktop library: '+name)
    shutil.copy2(src.resolve(),dest)
   queue.append(dest)
 (output/'tools-manifest.json').write_text(json.dumps(selected,indent=2)+'\n')
 subprocess.run(['tar','-C',str(output),'-czf',str(output/'tools.tar.gz'),'tools'],check=True)
 print('Signed ARM Wi-Fi, firewall, socket inspection tools, libraries and regulatory database prepared in build/wifi-native/')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Trim an already verified native package to network/firewall bootstrap files."""
import argparse,hashlib,json,re,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(source,output):
 with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='network-bootstrap-') as temp:
  root=Path(temp)
  with tarfile.open(source) as archive:archive.extractall(root,filter='data')
  usr=root/'tools/usr';files=set();queue=[]
  def add(path):
   path=Path(path)
   if path in files:return
   if not path.exists():raise ValueError('Missing bootstrap dependency: '+str(path.relative_to(root)))
   files.add(path)
   if path.is_symlink():add(path.resolve())
   elif path.is_file():queue.append(path)
  for name in ('iw','nft','wpa_supplicant','wpa_cli','ss','openssl'):add(usr/'bin'/name)
  add(usr/'lib/ld-linux-armhf.so.3')
  while queue:
   obj=queue.pop()
   with obj.open('rb') as stream:
    if stream.read(4)!=b'\x7fELF':continue
   dynamic=subprocess.check_output(['llvm-readelf','-d',str(obj)],text=True)
   for name in re.findall(r'Shared library: \[([^]]+)\]',dynamic):add(usr/'lib'/name)
  for path in (root/'modules').glob('*.ko'):add(path)
  for path in (usr/'lib/firmware').glob('regulatory.db*'):add(path)
  with tarfile.open(output,'w:gz') as archive:
   def owned(info):
    info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=0
    info.mode &= 0o755
    return info
   for path in sorted(files):archive.add(path,arcname=str(path.relative_to(root)),recursive=False,filter=owned)
 return hashlib.file_digest(output.open('rb'),'sha256').hexdigest()
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 print(build(a.source,a.output));print('Network bootstrap bytes:',a.output.stat().st_size)

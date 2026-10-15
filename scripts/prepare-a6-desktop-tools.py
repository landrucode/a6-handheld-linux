#!/usr/bin/env python3
"""Verify signed notification tools and extract only their runtime files."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import subprocess
import tarfile
ROOT=Path(__file__).resolve().parents[1]
spec=json.loads((ROOT/'rootfs/arch-desktop-tools-packages.json').read_text())
stage=ROOT/'build/desktop-tools'; stage.mkdir(parents=True,exist_ok=True)
runtime=stage/'runtime'; runtime.mkdir(exist_ok=True)
for name,package in spec['packages'].items():
    archive=stage/(name+'.pkg.tar.xz')
    for suffix in ('','.sig'):
        target=Path(str(archive)+suffix)
        cached=ROOT/'build/arch-bootstrap/downloads'/(package['filename']+suffix)
        if not target.exists() and cached.is_file():shutil.copyfile(cached,target)
        if not target.exists():
            partial=Path(str(target)+'.partial')
            subprocess.run(['curl','-fsSL',package.get('mirror',spec['mirror'])+package['filename']+suffix,'-o',str(partial)],check=True)
            partial.replace(target)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=package['sha256']:raise ValueError('Wrong '+name+' package')
    checked=subprocess.run(['gpg','--homedir',str(ROOT/'build/arch-bootstrap/gnupg'),'--batch','--status-fd','1','--verify',str(archive)+'.sig',str(archive)],capture_output=True,text=True,check=True)
    if not any(line.startswith('[GNUPG:] VALIDSIG '+spec['signing_fingerprint']+' ') for line in checked.stdout.splitlines()):raise ValueError('Wrong signer')
    with tarfile.open(archive) as tar:
        for member in tar:
            path=PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe package path')
            if not (str(path) in ('usr/bin/mako','usr/bin/makoctl','usr/bin/notify-send','usr/bin/swayidle','usr/bin/wlopm') or str(path).startswith(('usr/lib/libnotify.so','usr/lib/libsystemd.so'))):continue
            target=runtime/path;target.parent.mkdir(parents=True,exist_ok=True)
            if member.isfile():
                target.write_bytes(tar.extractfile(member).read());target.chmod(member.mode&0o777)
            elif member.issym():
                if '/' in member.linkname:raise ValueError('Unsafe symlink')
                target.unlink(missing_ok=True);target.symlink_to(member.linkname)
            else:raise ValueError('Unexpected runtime entry')
print('Signed notification and idle-blanking runtime verified')

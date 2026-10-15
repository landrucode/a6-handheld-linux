#!/usr/bin/env python3
"""Sign fixed RAM update artifacts; private key remains outside the repository."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'build'):
        raise ValueError('Update output must stay in ignored build/')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    key=Path.home()/'.a6-update-signing.key'
    info=key.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
        raise ValueError('Signing key must be owner-only regular file')
    sources={'a6-wifi.img3':ROOT/'build/arm/a6-wifi-brcmfmac.img3',
             'a6-desktop.squashfs':ROOT/'build/arch-bootstrap/arch-hyprland-user-desktop-native.squashfs'}
    lines=[]
    for name,source in sources.items():
        shutil.copy2(source,output/name)
        lines.append(hashlib.file_digest((output/name).open('rb'),'sha256').hexdigest()+'  '+name)
    manifest=output/'manifest.sha256';manifest.write_text('\n'.join(lines)+'\n')
    subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(key),'-in',str(manifest),'-out',str(output/'manifest.sig')],check=True)
    subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(ROOT/'build/wifi-boot-assets/update-public.pem'),'-in',str(manifest),'-sigfile',str(output/'manifest.sig')],check=True,stdout=subprocess.DEVNULL)
    print('Signed image/root manifest verified; existing image remains the fallback.')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Public RAM boot assets; no Wi-Fi configuration is read or bundled."""
import os
import hashlib
from pathlib import Path
import stat
import struct
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    output=ROOT/'build/wifi-boot-assets'
    output.mkdir(parents=True,exist_ok=True)
    desktop=ROOT/'build/arch-bootstrap/arch-hyprland-user-desktop-native.squashfs'
    with desktop.open('rb') as stream:
        (output/'desktop.sha256').write_text(hashlib.file_digest(stream,'sha256').hexdigest()+'\n')
    private=Path.home()/'.a6-update-signing.key'
    if not private.exists():
        fd=os.open(private,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(private)],check=True)
    info=private.stat()
    if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or not stat.S_ISREG(info.st_mode):
        raise ValueError('Signing key must be user-owned regular mode600')
    subprocess.run(['openssl','pkey','-in',str(private),'-pubout','-out',str(output/'update-public.pem')],check=True,stdout=subprocess.DEVNULL)
    for name,length in [('country',12),('mpc',4)]:
        for setting in [False,True]:
            header=struct.pack('<IIIII',263 if setting else 262,length+len(name)+1 if setting else length,20,int(setting),0)
            body=name.encode()+b'\0'
            (output/(name+('-set.prefix' if setting else '-get.ioctl'))).write_bytes(header+(body if setting else body.ljust(max(length,len(body)),b'\0')))
    (output/'country-gb.ioctl').write_bytes((output/'country-set.prefix').read_bytes()+b'GB\0\0'+struct.pack('<i',-1)+b'GB\0\0')
    (output/'mpc-off.ioctl').write_bytes((output/'mpc-set.prefix').read_bytes()+b'\0'*4)
    print('Public boot ioctl assets and update verification key prepared; no Wi-Fi secrets bundled.')
if __name__=='__main__':main()

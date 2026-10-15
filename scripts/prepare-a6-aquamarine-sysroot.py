#!/usr/bin/env python3
"""Prepare host-only ARM headers/link libraries from pinned signed packages."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

repo = Path(__file__).resolve().parents[1]
cache = repo/'build/arch-bootstrap'
root = repo/'build/aquamarine-sysroot'
root.mkdir(exist_ok=True)
manifest = json.loads((repo/'rootfs/arch-aquamarine-build-packages.json').read_text())
for name, spec in manifest['packages'].items():
    archive = cache/'downloads'/spec['filename']
    for suffix in ('', '.sig'):
        dest = Path(str(archive)+suffix)
        if not dest.exists():
            temporary = Path(str(dest)+'.partial')
            subprocess.run(['curl', '-fLsS', '--max-time', '120',
                manifest['mirror']+spec['repo']+'/'+spec['filename']+suffix,
                '-o', str(temporary)], check=True)
            temporary.replace(dest)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != spec['sha256']:
        raise RuntimeError(f'changed package: {name}')
    result = subprocess.run(['gpg', '--homedir', str(cache/'gnupg'), '--batch',
        '--status-fd', '1', '--verify', str(archive)+'.sig', str(archive)],
        capture_output=True, text=True, check=True)
    if not any(manifest['signing_fingerprint'] in line.split()
               for line in result.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')):
        raise RuntimeError(f'unexpected signer: {name}')
    with tarfile.open(archive) as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise RuntimeError('unsafe package path')
            selected = member.name.startswith(('usr/include/', 'usr/share/pkgconfig/',
                'usr/share/wayland/', 'usr/share/wayland-protocols/', 'usr/share/hwdata/'))
            selected |= member.name.startswith('usr/lib/') and (
                '.so' in path.name or path.suffix in ('.a', '.o', '.h', '.pc'))
            if not selected or member.isdir():
                continue
            dest = root/member.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.parent.resolve().is_relative_to(root):
                raise RuntimeError('escaped destination')
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            if member.isfile() or member.islnk():
                if member.islnk():
                    target = PurePosixPath(member.linkname)
                    if target.is_absolute() or '..' in target.parts:
                        raise RuntimeError('unsafe hardlink')
                dest.write_bytes(source.extractfile(member).read())
                dest.chmod(member.mode & 0o777)
            elif member.issym():
                target = member.linkname
                if target.startswith('/'):
                    target = os.path.relpath(root/target.lstrip('/'), dest.parent)
                if not (dest.parent/target).resolve().is_relative_to(root):
                    raise RuntimeError('escaped link')
                dest.symlink_to(target)
            else:
                raise RuntimeError(f'unsupported member: {member.name}')
for name in ('lib', 'lib32'):
    path = root/name
    if not path.exists():
        path.symlink_to('usr/lib')
print(root)

#!/usr/bin/env python3
"""Prepare a pinned, signature-verified minimal Arch ARM runtime for phone RAM.

Does not install packages on the host or contact/reset the phone. Package install
scripts are not run. This is a Bash runtime, not a complete Arch installation.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

repo = Path(__file__).resolve().parents[1]
manifest = json.loads((repo / 'rootfs/arch-bootstrap-packages.json').read_text())
output = repo / 'build/arch-bootstrap'
downloads = output / 'downloads'
downloads.mkdir(parents=True, exist_ok=True)
home = output / 'gnupg'
home.mkdir(mode=0o700, exist_ok=True)
for spec in manifest['packages'].values():
    for suffix in ('', '.sig'):
        filename = spec['filename'] + suffix
        target = downloads / filename
        if not target.exists():
            partial = target.with_name(filename + '.partial')
            subprocess.run(['curl', '-fLsS', '--max-time', '120',
                            manifest['mirror'] + filename, '-o', str(partial)], check=True)
            partial.replace(target)
    target = downloads / spec['filename']
    if hashlib.sha256(target.read_bytes()).hexdigest() != spec['sha256']:
        raise RuntimeError(f'package checksum mismatch: {target}')

# The downloaded keyring is only a source of public key bytes. Trust comes from
# requiring the exact build-system fingerprint published on the official site.
with tarfile.open(downloads / manifest['packages']['archlinuxarm-keyring']['filename']) as archive:
    keys = archive.extractfile('usr/share/pacman/keyrings/archlinuxarm.gpg').read()
keyfile = output / 'archlinuxarm.gpg'
keyfile.write_bytes(keys)
subprocess.run(['gpg', '--homedir', str(home), '--batch', '--import', str(keyfile)], check=True)
for name, spec in manifest['packages'].items():
    target = downloads / spec['filename']
    result = subprocess.run(['gpg', '--homedir', str(home), '--batch', '--status-fd', '1',
                             '--verify', str(target) + '.sig', str(target)],
                            capture_output=True, text=True, check=True)
    signatures = [line.split() for line in result.stdout.splitlines()
                  if line.startswith('[GNUPG:] VALIDSIG ')]
    if not any(parts[2] == manifest['signing_fingerprint'] or
               parts[-1] == manifest['signing_fingerprint'] for parts in signatures):
        raise RuntimeError(f'unexpected package signer: {name}')
    (output / (name + '-signature.txt')).write_text(result.stdout + result.stderr)
    print(f'Verified {name}', flush=True)

members = {
    'bash': ['usr/bin/bash'],
    'glibc': ['usr/lib/ld-linux-armhf.so.3', 'usr/lib/libc.so.6'],
    'ncurses': ['usr/lib/libncursesw.so.6.6'],
    'readline': ['usr/lib/libreadline.so.8.3'],
    'libgcc': ['usr/lib/libgcc_s.so.1'],
}
links = {
    'bin': 'usr/bin', 'lib': 'usr/lib',
    'usr/lib/libncursesw.so.6': 'libncursesw.so.6.6',
    'usr/lib/libtinfo.so.6': 'libncursesw.so.6.6',
    'usr/lib/libreadline.so.8': 'libreadline.so.8.3',
}
bundle = output / 'arch-runtime.tar.gz'
with bundle.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
    with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as result:
        for directory in ('', 'usr', 'usr/bin', 'usr/lib', 'dev'):
            info = tarfile.TarInfo('arch-runtime/' + directory)
            info.type, info.mode = tarfile.DIRTYPE, 0o755
            result.addfile(info)
        # Bash redirects asynchronous commands from /dev/null without job control.
        info = tarfile.TarInfo('arch-runtime/dev/null')
        info.type, info.mode = tarfile.CHRTYPE, 0o666
        info.devmajor, info.devminor = 1, 3
        result.addfile(info)
        for package, paths in members.items():
            with tarfile.open(downloads / manifest['packages'][package]['filename']) as source:
                for path in paths:
                    member = source.getmember(path)
                    if not member.isfile():
                        raise RuntimeError(f'expected regular file: {path}')
                    data = source.extractfile(member).read()
                    info = tarfile.TarInfo('arch-runtime/' + path)
                    info.size, info.mode = len(data), 0o755
                    result.addfile(info, io.BytesIO(data))
        for path, target in links.items():
            info = tarfile.TarInfo('arch-runtime/' + path)
            info.type, info.mode, info.linkname = tarfile.SYMTYPE, 0o777, target
            result.addfile(info)
        data = (repo / 'rootfs/a6-arch-smoke.sh').read_bytes()
        info = tarfile.TarInfo('arch-runtime/arch-smoke.sh')
        info.size, info.mode = len(data), 0o755
        result.addfile(info, io.BytesIO(data))
digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
(output / 'arch-runtime.sha256').write_text(f'{digest}  {bundle.name}\n')
print(f'{bundle}: {bundle.stat().st_size} bytes, SHA256 {digest}')

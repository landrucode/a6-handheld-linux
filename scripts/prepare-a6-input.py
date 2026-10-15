#!/usr/bin/env python3
"""Prepare a signed Arch xdotool overlay for the existing RAM graphics root."""
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

repo = Path(__file__).resolve().parents[1]
out = repo / 'build/arch-bootstrap'
manifest = json.loads((repo / 'rootfs/arch-input-packages.json').read_text())
with tempfile.TemporaryDirectory(dir=out, prefix='input-stage-') as temp:
    root = Path(temp) / 'input-runtime'
    root.mkdir()
    for name, spec in manifest['packages'].items():
        archive = out / 'downloads' / spec['filename']
        for suffix in ('', '.sig'):
            dest = Path(str(archive) + suffix)
            if not dest.exists():
                partial = Path(str(dest) + '.partial')
                subprocess.run(['curl', '-fLsS', '--max-time', '120', manifest['mirror'] + spec['repo'] + '/' + spec['filename'] + suffix, '-o', str(partial)], check=True)
                partial.replace(dest)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != spec['sha256']:
            raise RuntimeError(f'checksum mismatch: {name}')
        result = subprocess.run(['gpg', '--homedir', str(out / 'gnupg'), '--batch', '--status-fd', '1', '--verify', str(archive) + '.sig', str(archive)], capture_output=True, text=True, check=True)
        signatures = [line.split() for line in result.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
        if not any(s[2] == manifest['signing_fingerprint'] or s[-1] == manifest['signing_fingerprint'] for s in signatures):
            raise RuntimeError(f'unexpected signer: {name}')
        (out / (name + '-signature.txt')).write_text(result.stdout + result.stderr)
        with tarfile.open(archive) as source:
            for member in source:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts:
                    raise RuntimeError('unsafe package path')
                if not (member.name == 'usr/bin/xdotool' or (member.name.startswith('usr/lib/') and '.so' in path.name)):
                    continue
                dest = root / member.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.parent.resolve().is_relative_to(root):
                    raise RuntimeError('escaped destination')
                if member.isfile():
                    dest.write_bytes(source.extractfile(member).read())
                    dest.chmod(member.mode & 0o777)
                elif member.issym():
                    target = member.linkname
                    if target.startswith('/'):
                        target = os.path.relpath(root / target.lstrip('/'), dest.parent)
                    if not (dest.parent / target).resolve().is_relative_to(root):
                        raise RuntimeError('escaped link')
                    dest.symlink_to(target)
    with tarfile.open(out / 'arch-graphics.tar.gz') as base:
        available = {PurePosixPath(m.name).name for m in base if '/usr/lib/' in m.name}
    pending = [root / 'usr/bin/xdotool']
    required = set()
    while pending:
        path = pending.pop()
        if path in required:
            continue
        required.add(path)
        if path.is_symlink():
            pending.append(path.resolve())
            continue
        result = subprocess.run(['readelf', '-d', str(path)], capture_output=True, text=True, check=True)
        for name in re.findall(r'Shared library: \[(.*?)\]', result.stdout):
            local = root / 'usr/lib' / name
            if local.exists():
                pending.append(local)
            elif name not in available:
                raise RuntimeError(f'{path.name} missing {name}')
    for path in (root / 'usr/lib').iterdir():
        if path not in required:
            path.unlink()
    def metadata(info):
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        return info
    bundle = out / 'arch-input.tar.gz'
    with bundle.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            archive.add(root / 'usr', arcname='usr', filter=metadata)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (out / 'arch-input.sha256').write_text(f'{digest}  {bundle.name}\n')
    print(f'{bundle.stat().st_size} bytes; SHA256 {digest}')

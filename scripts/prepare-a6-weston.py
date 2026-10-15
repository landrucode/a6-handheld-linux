#!/usr/bin/env python3
"""Prepare signed Weston software/X11 compositor overlay for the RAM graphics root."""
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
manifest = json.loads((repo / 'rootfs/arch-weston-packages.json').read_text())
with tempfile.TemporaryDirectory(dir=out, prefix='weston-stage-') as temp:
    root = Path(temp) / 'weston-runtime'
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
                if member.name.startswith('usr/share/weston/') and member.isfile():
                    dest = root / member.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(source.extractfile(member).read())
                    continue
                if not (member.name in ('usr/bin/weston', 'usr/bin/weston-simple-shm', 'usr/bin/weston-terminal') or (member.name.startswith('usr/lib/') and '.so' in path.name)):
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
    for bundle in ('arch-input.tar.gz',):
        with tarfile.open(out / bundle) as base:
            available |= {PurePosixPath(m.name).name for m in base if '/usr/lib/' in m.name}
    pending = [root / name for name in ('usr/bin/weston', 'usr/bin/weston-simple-shm', 'usr/bin/weston-terminal', 'usr/lib/libweston-15/x11-backend.so', 'usr/lib/weston/desktop-shell.so', 'usr/lib/weston/kiosk-shell.so')]
    required = set()
    missing = set()
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
            if not local.exists():
                matches = list((root / 'usr/lib').rglob(name))
                if len(matches) == 1:
                    local = matches[0]
            if local.exists():
                pending.append(local)
            elif name not in available:
                missing.add(name)
    if missing:
        raise RuntimeError(f'missing libraries: {sorted(missing)}')
    for path in (root / 'usr/lib').rglob('*'):
        if not path.is_dir() and path not in required:
            path.unlink()
    # Never replace libraries backing the live Xorg process. Verify that any
    # overlapping file is identical, then omit it from this additive overlay.
    existing = {}
    links = {}
    for filename, prefix in (('arch-graphics.tar.gz', 'graphics-runtime/'), ('arch-input.tar.gz', '')):
        with tarfile.open(out / filename) as base:
            for member in base:
                name = member.name.removeprefix(prefix)
                if member.isfile():
                    existing[name] = hashlib.sha256(base.extractfile(member).read()).hexdigest()
                elif member.issym():
                    links[name] = os.path.normpath(str(PurePosixPath(name).parent / member.linkname))
    for name, target in links.items():
        if target in existing:
            existing[name] = existing[target]
    remove = []
    for path in root.rglob('*'):
        name = str(path.relative_to(root))
        if name in existing:
            if hashlib.sha256(path.read_bytes()).hexdigest() != existing[name]:
                raise RuntimeError(f'overlay would change live library: {name}')
            remove.append(path)
    for path in remove:
        path.unlink()
    size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())
    if size > 20 * 1024 * 1024:
        raise RuntimeError(f'overlay exceeds RAM budget: {size}')
    print(f'Extracted overlay bytes: {size}')
    def metadata(info):
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        return info
    bundle = out / 'arch-weston.tar.gz'
    with bundle.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            archive.add(root / 'usr', arcname='usr', filter=metadata)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (out / 'arch-weston.sha256').write_text(f'{digest}  {bundle.name}\n')
    print(f'{bundle.stat().st_size} bytes; SHA256 {digest}')

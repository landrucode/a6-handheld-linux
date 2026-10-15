#!/usr/bin/env python3
"""Build a small signature-verified Arch Xorg/fbdev/xterm runtime for phone RAM.

No package scripts, host installation, phone access or device writes. This
runtime is an experiment; it is not a complete pacman-managed installation.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

repo = Path(__file__).resolve().parents[1]
out = repo / 'build/arch-bootstrap'
subprocess.run(['python3', str(repo / 'scripts/prepare-a6-arch-runtime.py')], check=True)
base = json.loads((repo / 'rootfs/arch-bootstrap-packages.json').read_text())
manifest = json.loads((repo / 'rootfs/arch-graphics-packages.json').read_text())
packages = dict(manifest['packages'])
packages.update({name: dict(spec, repo='core') for name, spec in base['packages'].items()})
downloads = out / 'downloads'
for name, spec in packages.items():
    target = downloads / spec['filename']
    for suffix in ('', '.sig'):
        dest = Path(str(target) + suffix)
        if not dest.exists():
            partial = Path(str(dest) + '.partial')
            url = manifest['mirror'] + spec['repo'] + '/' + spec['filename'] + suffix
            subprocess.run(['curl', '-fLsS', '--max-time', '120', url, '-o', str(partial)], check=True)
            partial.replace(dest)
    if hashlib.sha256(target.read_bytes()).hexdigest() != spec['sha256']:
        raise RuntimeError(f'checksum mismatch: {name}')
    result = subprocess.run(['gpg', '--homedir', str(out / 'gnupg'), '--batch',
                             '--status-fd', '1', '--verify', str(target) + '.sig', str(target)],
                            capture_output=True, text=True, check=True)
    signatures = [line.split() for line in result.stdout.splitlines()
                  if line.startswith('[GNUPG:] VALIDSIG ')]
    if not any(parts[2] == manifest['signing_fingerprint'] or
               parts[-1] == manifest['signing_fingerprint'] for parts in signatures):
        raise RuntimeError(f'unexpected package signer: {name}')
    (out / (name + '-signature.txt')).write_text(result.stdout + result.stderr)

seeds = ['usr/lib/Xorg', 'usr/bin/xterm', 'usr/bin/xkbcomp', 'usr/bin/bash',
         'usr/lib/xorg/modules/drivers/fbdev_drv.so',
         'usr/lib/xorg/modules/libfbdevhw.so', 'usr/lib/xorg/modules/libshadow.so',
         'usr/lib/xorg/modules/libshadowfb.so']
with tempfile.TemporaryDirectory(prefix='graphics-stage-', dir=out) as temporary:
    work = Path(temporary)
    pool, root = work / 'pool', work / 'graphics-runtime'
    pool.mkdir()
    root.mkdir()
    for spec in packages.values():
        with tarfile.open(downloads / spec['filename']) as archive:
            for member in archive:
                name = member.name
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts:
                    raise RuntimeError(f'unsafe package path: {name}')
                include = (name.startswith('usr/lib/') and '.so' in path.name) or name in seeds
                include |= name.startswith(('usr/share/xkeyboard-config-', 'usr/share/fonts/misc/',
                                            'usr/share/terminfo/x/', 'usr/share/terminfo/l/'))
                if not include or member.isdir():
                    continue
                dest = pool / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.parent.resolve().is_relative_to(pool):
                    raise RuntimeError(f'escaped package destination: {name}')
                if dest.is_symlink():
                    dest.unlink()
                if member.isfile():
                    dest.write_bytes(archive.extractfile(member).read())
                    dest.chmod(member.mode & 0o777)
                elif member.issym():
                    target = member.linkname
                    if target.startswith('/'):
                        target = os.path.relpath(pool / target.lstrip('/'), dest.parent)
                    if not (dest.parent / target).resolve().is_relative_to(pool):
                        raise RuntimeError(f'escaped package link: {name}')
                    dest.symlink_to(target)

    pending = [pool / name for name in seeds]
    closure = set()
    while pending:
        source = pending.pop()
        if source in closure:
            continue
        if not source.exists():
            raise RuntimeError(f'missing ELF dependency: {source.name}')
        closure.add(source)
        result = subprocess.run(['readelf', '-d', str(source)], capture_output=True,
                                text=True, check=True)
        for name in re.findall(r'Shared library: \[(.*?)\]', result.stdout):
            pending.append(pool / 'usr/lib' / name)
    for source in sorted(closure):
        dest = root / source.relative_to(pool)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        dest.chmod(0o755)
    (out / 'graphics-closure.txt').write_text('\n'.join(
        str(source.relative_to(pool)) for source in sorted(closure)) + '\n')

    shutil.copytree(pool / 'usr/share/xkeyboard-config-2', root / 'usr/share/xkeyboard-config-2')
    shutil.copytree(pool / 'usr/share/terminfo', root / 'usr/share/terminfo')
    fonts = root / 'usr/share/fonts/misc'
    fonts.mkdir(parents=True)
    entries = []
    for name, xlfd in [
        ('6x13-ISO8859-1.pcf.gz', '-misc-fixed-medium-r-normal--13-120-75-75-c-60-iso8859-1'),
        ('8x13-ISO8859-1.pcf.gz', '-misc-fixed-medium-r-normal--13-120-75-75-c-80-iso8859-1'),
        ('cursor.pcf.gz', 'cursor'),
    ]:
        shutil.copyfile(pool / 'usr/share/fonts/misc' / name, fonts / name)
        entries.append(name + ' ' + xlfd)
    (fonts / 'fonts.dir').write_text(str(len(entries)) + '\n' + '\n'.join(entries) + '\n')
    (fonts / 'fonts.alias').write_text('fixed -misc-fixed-medium-r-normal--13-120-75-75-c-60-iso8859-1\n')
    for name in ('etc/X11', 'dev', 'proc', 'sys', 'tmp', 'var/log', 'var/run', 'root', 'usr/share/X11'):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name, target in [('lib', 'usr/lib'), ('bin', 'usr/bin'), ('usr/bin/sh', 'bash'),
                         ('usr/share/X11/xkb', '../xkeyboard-config-2')]:
        (root / name).symlink_to(target)
    (root / 'tmp').chmod(0o1777)
    (root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\n')
    (root / 'etc/group').write_text('root:x:0:\n')
    (root / 'etc/nsswitch.conf').write_text('passwd: files\ngroup: files\nhosts: files dns\n')
    (root / 'etc/hosts').write_text('127.0.0.1 localhost\n')
    shutil.copyfile(repo / 'rootfs/a6-xorg.conf', root / 'etc/X11/xorg.conf')
    shutil.copyfile(repo / 'rootfs/a6-xterm-launch.sh', root / 'launch-xterm.sh')
    (root / 'launch-xterm.sh').chmod(0o755)
    size = sum(path.stat().st_size for path in root.rglob('*')
               if path.is_file() and not path.is_symlink())
    if size > 32 * 1024 * 1024:
        raise RuntimeError(f'graphics runtime exceeds 32 MiB budget: {size}')

    def metadata(info):
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        return info

    bundle = out / 'arch-graphics.tar.gz'
    with bundle.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            archive.add(root, arcname='graphics-runtime', filter=metadata)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (out / 'arch-graphics.sha256').write_text(f'{digest}  {bundle.name}\n')
    print(f'Verified {len(packages)} packages; ELF closure {len(closure)} files.')
    print(f'Runtime {size} bytes; archive {bundle.stat().st_size} bytes; SHA256 {digest}')

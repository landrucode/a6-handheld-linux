#!/usr/bin/env python3
"""Bundle the checked RAM desktop overlays for one-transfer reload after a boot.

No device access, private keys, pseudo filesystems, or package install scripts.
"""
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
import tarfile
import tempfile

repo = Path(__file__).resolve().parents[1]
out = repo/'build/arch-bootstrap'
names = ('graphics', 'input', 'weston', 'tools', 'ssh', 'foot', 'drm')
subprocess.run(['bash', str(repo/'scripts/build-a6-uinput.sh')], check=True)
with tempfile.TemporaryDirectory(dir=out, prefix='desktop-stage-') as temporary:
    stage = Path(temporary)
    checks = {}
    for name in names:
        archive = out/f'arch-{name}.tar.gz'
        expected = (out/f'arch-{name}.sha256').read_text().split()[0]
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != expected:
            raise RuntimeError(f'changed overlay: {name}')
        checks[name] = digest
        target = stage if name == 'graphics' else stage/'graphics-runtime'
        with tarfile.open(archive) as source:
            source.extractall(target, filter='data')
    root = stage/'graphics-runtime'
    for source, destination in (
        ('desktop/theme/foot.ini', 'root/.config/foot/foot.ini'),
        ('rootfs/a6-fonts.conf', 'etc/fonts/fonts.conf')):
        dest = root/destination
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((repo/source).read_bytes())
    (root/'etc/shells').write_text('/bin/bash\n')
    probe = root/'usr/local/share/a6/hyprland.lua'
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_bytes((repo/'rootfs/a6-hyprland.lua').read_bytes())
    local_helpers = {}
    for source, destination in (
        ('build/arm/a6-uinput', 'usr/local/bin/a6-uinput'),
        ('rootfs/a6-label-input.sh', 'usr/local/bin/a6-label-input'),
        ('rootfs/a6-start-desktop.sh', 'usr/local/bin/a6-start-desktop')):
        data = (repo/source).read_bytes()
        dest = root/destination
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        dest.chmod(0o755)
        local_helpers[destination] = hashlib.sha256(data).hexdigest()
    for directory in ('dev', 'proc', 'sys', 'tmp', 'root/.ssh', 'etc/dropbear', 'var/run'):
        (root/directory).mkdir(parents=True, exist_ok=True)
    (root/'root').chmod(0o700)
    (root/'root/.ssh').chmod(0o700)
    size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())
    if size > 128*1024*1024:
        raise RuntimeError(f'desktop exceeds128 MiB staged bound: {size}')
    # Public keys are provisioned separately; no SSH identity travels in bundle.
    assert not list(root.rglob('*host_key'))
    assert not (root/'root/.ssh/authorized_keys').exists()
    def metadata(info):
        info.uid=info.gid=info.mtime=0
        info.uname=info.gname=''
        return info
    bundle=out/'arch-desktop.tar.gz'
    with bundle.open('wb') as stream, gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            archive.add(root,arcname='graphics-runtime',filter=metadata)
    digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
    (out/'arch-desktop.sha256').write_text(f'{digest}  {bundle.name}\n')
    (out/'arch-desktop-manifest.json').write_text(json.dumps({'overlays':checks,'local_helpers':local_helpers,'regular_file_bytes':size,'sha256':digest},indent=2)+'\n')
    print(f'{size} extracted bytes; {bundle.stat().st_size} compressed; SHA256 {digest}')

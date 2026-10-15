#!/usr/bin/env python3
"""Bundle the proven optional Hyprland stack for a fresh RAM root, without keys."""
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

repo=Path(__file__).resolve().parents[1]
out=repo/'build/arch-bootstrap'
candidate=repo/'build/arm/aquamarine-simpledrm'
provenance=json.loads((candidate/'manifest.json').read_text())
binary=candidate/'libaquamarine.so.0.15.1'
assert hashlib.sha256(binary.read_bytes()).hexdigest()==provenance['sha256']
assert provenance['source_commit']=='f31c47a1b9d300847d8fc3108ad959448103dfc1'
for name,digest in provenance['patches'].items():
    assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,name
with tempfile.TemporaryDirectory(dir=out,prefix='hyprland-desktop-stage-') as temporary:
    stage=Path(temporary)
    inputs={}
    for name in ('desktop','egl','hyprland'):
        source=out/f'arch-{name}.tar.gz'
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        assert digest==(out/f'arch-{name}.sha256').read_text().split()[0]
        inputs[name]=digest
        with tarfile.open(source) as archive:
            archive.extractall(stage if name=='desktop' else stage/'graphics-runtime',filter='data')
    root=stage/'graphics-runtime'
    dest=root/'opt/a6/aquamarine-simpledrm'
    dest.mkdir(parents=True)
    (dest/binary.name).write_bytes(binary.read_bytes())
    (dest/binary.name).chmod(0o755)
    (dest/'libaquamarine.so.14').symlink_to(binary.name)
    (dest/'manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')
    assert not (root/'root/.ssh/authorized_keys').exists()
    assert not list(root.rglob('*host_key'))
    files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    size=sum((root/name).stat().st_size for name in files)
    assert size<384*1024*1024,size
    def metadata(info):
        info.uid=info.gid=info.mtime=0
        info.uname=info.gname=''
        return info
    bundle=out/'arch-hyprland-desktop.tar.gz'
    with bundle.open('wb') as stream, gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            archive.add(root,arcname='graphics-runtime',filter=metadata)
    digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
    (out/'arch-hyprland-desktop.sha256').write_text(f'{digest}  {bundle.name}\n')
    (out/'arch-hyprland-desktop-files.sha256').write_text(''.join(f'{v}  {k}\n' for k,v in files.items()))
    (out/'arch-hyprland-desktop-manifest.json').write_text(json.dumps(
        {'inputs':inputs,'aquamarine':provenance,'regular_file_bytes':size,
         'regular_file_count':len(files),'sha256':digest},indent=2)+'\n')
    print(f'{size} extracted bytes; {bundle.stat().st_size} compressed; SHA256 {digest}')

#!/usr/bin/env python3
"""Combine verified Arch/Hyprland and unprivileged desktop RAM overlays."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile

repo = Path(__file__).resolve().parents[1]
out = repo / 'build/arch-bootstrap'
base = out / 'arch-hyprland-desktop.tar.gz'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native', action='store_true')
args = parser.parse_args()
overlay_stem = 'arch-user-desktop-native' if args.native else 'arch-user-desktop'
result_stem = 'arch-hyprland-user-desktop-native' if args.native else 'arch-hyprland-user-desktop'
overlay = out / (overlay_stem + '.tar.gz')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


for archive in (base, overlay):
    expected = archive.with_suffix('').with_suffix('.sha256').read_text().split()[0]
    if digest(archive) != expected:
        raise RuntimeError(f'archive checksum mismatch: {archive}')

overlay_files = json.loads((out / (overlay_stem + '-manifest.json')).read_text())['files']
with tempfile.TemporaryDirectory(dir=out, prefix='hyprland-user-stage-') as temp:
    stage = Path(temp)
    with tarfile.open(base, 'r:gz') as source:
        source.extractall(stage, filter='data')
    root = stage / 'graphics-runtime'
    with tarfile.open(overlay, 'r:gz') as source:
        source.extractall(root, filter='data')
    for name, expected in overlay_files.items():
        if digest(root / name) != expected:
            raise RuntimeError(f'overlay file mismatch: {name}')
    if (root / 'root/.ssh/authorized_keys').exists() or list(root.rglob('*host_key')):
        raise RuntimeError('unexpected credentials in RAM bundle')

    files = {str(path.relative_to(root)): digest(path)
             for path in root.rglob('*') if path.is_file() and not path.is_symlink()}
    size = sum((root / name).stat().st_size for name in files)
    if size >= 384 * 1024 * 1024:
        raise RuntimeError(f'RAM-root payload too large: {size}')

    def metadata(info):
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        return info

    result = out / (result_stem + '.tar.gz')
    with result.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as target:
            target.add(root, arcname='graphics-runtime', filter=metadata)
    result_digest = digest(result)
    (out / (result_stem + '.sha256')).write_text(
        f'{result_digest}  {result.name}\n')
    (out / (result_stem + '-files.sha256')).write_text(
        ''.join(f'{value}  {name}\n' for name, value in sorted(files.items())))
    (out / (result_stem + '-manifest.json')).write_text(json.dumps({
        'base_sha256': digest(base),
        'overlay_sha256': digest(overlay),
        'sha256': result_digest,
        'regular_file_count': len(files),
        'regular_file_bytes': size,
    }, indent=2) + '\n')
    print(f'{result}: {result.stat().st_size} compressed bytes, '
          f'{size} regular-file bytes, SHA256 {result_digest}')

#!/usr/bin/env python3
"""Package the user-session and OSK additions; no account secrets or live state."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
repo = Path(__file__).resolve().parents[1]
out = repo / 'build/arch-bootstrap'
files = {
    'a6-start-desktop': 'rootfs/a6-start-desktop.sh',
    'a6-prepare-user-desktop': 'rootfs/a6-prepare-user-desktop.sh',
    'a6-start-user-hyprland': 'rootfs/a6-start-user-hyprland.sh',
    'a6-osk-receiver': 'rootfs/a6-osk-receiver.sh',
    'wvkbd-mobintl': 'build/arm/wvkbd-mobintl',
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native', action='store_true', help='add native keyboard profile in a separate archive')
args = parser.parse_args()
stem = 'arch-user-desktop-native' if args.native else 'arch-user-desktop'
if args.native:
    del files['wvkbd-mobintl']
    files['wvkbd-native'] = 'build/arm/wvkbd-native'
manifest = {}
bundle = out / (stem + '.tar.gz')
with bundle.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as gz:
    with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, source in sorted(files.items()):
            data = (repo / source).read_bytes()
            path = 'usr/local/bin/' + name
            entry = tarfile.TarInfo(path)
            entry.mode = 0o755
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
            manifest[path] = hashlib.sha256(data).hexdigest()
digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
(out/(stem+'.sha256')).write_text(f'{digest}  {bundle.name}\n')
(out/(stem+'-manifest.json')).write_text(json.dumps({'sha256':digest,'files':manifest},indent=2)+'\n')
print(f'{bundle.stat().st_size} bytes; SHA256 {digest}')

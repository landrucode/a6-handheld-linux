#!/usr/bin/env python3
"""Build a labwc-ready base from freshly generated, verified public overlays."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS_COMMIT = '99d23a31b471433c51e9c145aeba2ab1536e34df'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'build') or output.exists():
        raise ValueError('Use a new output under build/')
    tools = ROOT/'.deps/squashfs-tools-4.7.2'
    if subprocess.check_output(['git','-C',str(tools),'rev-parse','HEAD'],text=True).strip() != TOOLS_COMMIT:
        raise ValueError('Unexpected SquashFS tools revision')
    output.parent.mkdir(parents=True, exist_ok=True)
    inputs = {}
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='handheld-base-') as temporary:
        stage = Path(temporary)/'source'
        stage.mkdir()
        for stem in ('arch-desktop', 'arch-egl', 'arch-user-desktop-native'):
            archive = ROOT/'build/arch-bootstrap'/(stem+'.tar.gz')
            expected = archive.with_suffix('').with_suffix('.sha256').read_text().split()[0]
            if digest(archive) != expected:
                raise ValueError('Changed generated overlay: '+stem)
            inputs[stem] = expected
            target = stage if stem == 'arch-desktop' else stage/'graphics-runtime'
            with tarfile.open(archive) as source:
                source.extractall(target, filter='data')
        root = stage/'graphics-runtime'
        subprocess.run(['python3', str(ROOT/'scripts/prepare-a6-audio-runtime.py'),
                        '--desktop-libs', str(root/'usr/lib')], check=True)
        audio = ROOT/'build/audio-alsa-runtime/runtime'
        shutil.copytree(audio, root/'opt/a6/audio-runtime', symlinks=True)
        shutil.copyfile(ROOT/'rootfs/a6-audio-session.sh', root/'usr/local/bin/a6-audio-session')
        (root/'usr/local/bin/a6-audio-session').chmod(0o755)
        for path in (root/'opt/a6/audio-runtime').rglob('*'):
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
        inputs['audio_packages'] = json.loads((ROOT/'build/audio-alsa-runtime/manifest.json').read_text())
        hashes = {str(p.relative_to(stage)): digest(p) for p in stage.rglob('*')
                  if p.is_file() and not p.is_symlink()}
        subprocess.run([str(tools/'squashfs-tools/mksquashfs'),str(stage),str(output),
                        '-noappend','-all-root','-root-mode','0755','-no-xattrs',
                        '-comp','zstd','-Xcompression-level','15','-b','131072',
                        '-repro-time','0','-processors','2','-mem','256M','-no-progress'],
                       check=True, stdout=subprocess.DEVNULL)
        verified = Path(temporary)/'verified'
        subprocess.run([str(tools/'squashfs-tools/unsquashfs'),'-no-progress',
                        '-processors','2','-d',str(verified),str(output)],
                       check=True, stdout=subprocess.DEVNULL)
        for name, sha in hashes.items():
            if digest(verified/name) != sha:
                raise ValueError('Base round-trip mismatch: '+name)
    output.with_suffix('.json').write_text(json.dumps(dict(kind='a6-handheld-base',
        sha256=digest(output), bytes=output.stat().st_size, inputs=inputs,
        regular_files=len(hashes), round_trip_verified=True),indent=2)+'\n')
    print('Public-overlay handheld base built and round-trip verified', flush=True)

if __name__ == '__main__':
    main()

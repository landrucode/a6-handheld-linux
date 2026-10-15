#!/usr/bin/env python3
"""Build public desktop/browser inputs without an old image or prepared runtime.

No phone access, root privileges, private firmware or signing keys. Cached
signed package archives may be supplied; every preparation step re-verifies
hashes/signatures. Run in an isolated checkout to keep accepted outputs intact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-cache', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=ROOT/'build/handheld/desktop.squashfs')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'build') or output.exists():
        raise ValueError('Use a new output under build/')
    required = ('python3','git','curl','gpg','make','gcc','clang','clang++',
                'llvm-strip','llvm-readelf','pkg-config','wayland-scanner',
                'update-mime-database','ffmpeg','ffprobe')
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise ValueError('Missing host tools: '+', '.join(missing))
    sources = json.loads((ROOT/'rootfs/handheld-build-sources.json').read_text())
    (ROOT/'.deps').mkdir(exist_ok=True)
    for name, spec in sources.items():
        path = ROOT/'.deps'/name
        if not path.exists():
            subprocess.run(['git','clone','--filter=blob:none','--no-checkout',spec['url'],str(path)],check=True)
            subprocess.run(['git','-C',str(path),'checkout','--detach',spec['revision']],check=True)
        revision = subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        dirty = subprocess.check_output(['git','-C',str(path),'diff','HEAD','--'],text=True)
        if revision != spec['revision'] or dirty:
            raise ValueError('Unexpected/modified upstream source: '+name)
    downloads = ROOT/'build/arch-bootstrap/downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    for cache in args.package_cache:
        for path in cache.resolve().glob('*.pkg.tar.*'):
            if not path.is_file() or path.name.endswith(('.part','.partial')):
                continue
            target = downloads/path.name
            if not target.exists():
                shutil.copyfile(path, target)
    output.parent.mkdir(parents=True, exist_ok=True)
    logs = output.parent/'build-logs'
    logs.mkdir(exist_ok=True)
    results = []
    def run(name, command):
        print('BUILD '+name, flush=True)
        started = time.monotonic()
        with (logs/(name+'.log')).open('w') as log:
            result = subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        results.append(dict(step=name,seconds=round(time.monotonic()-started,2),returncode=result.returncode))
        (logs/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        if result.returncode:
            raise RuntimeError('Build failed: '+name+'; see its build log')
    run('squashfs-tools',['make','-C',str(ROOT/'.deps/squashfs-tools-4.7.2/squashfs-tools'),'-j4'])
    for name in ('graphics','input','weston','tools','ssh','foot','drm','egl','aquamarine-sysroot'):
        run(name,['python3','scripts/prepare-a6-'+name+'.py'])
    run('keyboard',['env','A6_WVKBD_PROFILE=native','A6_WVKBD_POLL_CANDIDATE=1','bash','scripts/build-a6-wvkbd.sh'])
    run('oomd',['python3','scripts/build-a6-oomd.py'])
    run('base-overlays',['python3','scripts/prepare-a6-desktop.py'])
    run('user-session',['python3','scripts/prepare-a6-user-desktop.py','--native'])
    base = output.parent/'desktop-base.squashfs'
    run('audio-base',['python3','scripts/build-a6-handheld-base.py','--output',str(base)])
    run('labwc-panel',['bash','scripts/build-a6-labwc-panel.sh'])
    run('desktop-tools',['python3','scripts/prepare-a6-desktop-tools.py'])
    run('user-tools',['python3','scripts/prepare-a6-user-tools.py'])
    run('public-video-fixtures',['bash','scripts/build-a6-local-video.sh'])
    run('media',['python3','scripts/prepare-a6-media-runtime.py','--desktop-base',str(base)])
    run('desktop',['python3','scripts/refresh-a6-desktop-squashfs.py','--source',str(base),
                   '--output',str(output),'--compositor','labwc','--reuse-components'])
    run('browser',['python3','scripts/prepare-a6-browser-runtime.py'])
    report = dict(desktop_sha256=digest(output),desktop_bytes=output.stat().st_size,
                  browser_sha256=digest(ROOT/'build/epiphany-runtime/browser.squashfs'),
                  browser_bytes=(ROOT/'build/epiphany-runtime/browser.squashfs').stat().st_size,
                  sources=sources,steps=results,phone_tested=False,
                  old_images_or_prepared_runtimes_used=False)
    output.with_suffix('.source-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Desktop/browser rebuilt from public sources and signed package inputs; hardware promotion remains separate',flush=True)

if __name__ == '__main__':
    main()

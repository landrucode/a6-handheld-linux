#!/usr/bin/env python3
"""Sign and select verified RAM boot bundles on the host; never reboot a phone."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import tarfile
import io

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'build/wifi-boot-assets/update-public.pem'
FILES = ('a6-wifi.img3', 'a6-desktop.squashfs', 'modules.tar.gz', 'manifest.json',
         'firewall-modules.json', 'manifest.sha256', 'manifest.sig')

AUXILIARY = ('browser.squashfs', 'time-runtime.tar.gz')
APP_HELPERS = ('a6-wifi-recover.sh','a6-wifi-health.sh','a6-wifi-off.sh','a6-power-longrun.sh','a6-wifi-boot.sh','a6-start-native-desktop.sh','a6-desktop-memory.sh','a6-release-boot-staging.sh','a6-desktop-workload-log.sh','a6-browser-state-watch.sh','a6-mount-compressed-desktop.sh','a6-start-app-services.sh','a6-notify-browser-pressure.sh',
               'a6-browser-memory-watch.sh','a6-launch-browser-test.sh',
               'a6-browser-enter-root.sh','a6-browser-extra-swap.sh')

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT / 'build'):
        raise ValueError('RAM boot bundles belong in ignored build/')
    return path


def verify(bundle):
    bundle = local(bundle)
    for name in (*FILES, 'release.json', 'release.sig'):
        info = (bundle / name).lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Bundle entries must be regular files')
    subprocess.run(['openssl', 'pkeyutl', '-verify', '-rawin', '-pubin', '-inkey', str(PUBLIC),
                    '-in', str(bundle / 'release.json'), '-sigfile', str(bundle / 'release.sig')],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = json.loads((bundle / 'release.json').read_text())
    if set(data) != {'format', 'files'} or data['format'] not in (1, 2, 3, 4) or set(data['files']) != set(FILES if data['format'] == 1 else (*FILES, *AUXILIARY, *(() if data['format'] == 2 else (('app-helpers.tar.gz',) if data['format']==3 else ('app-helpers.tar.gz','network-bootstrap.tar.gz'))))):
        raise ValueError('Unexpected signed bundle format')
    for name in data['files']:
        if not stat.S_ISREG((bundle / name).lstat().st_mode):
            raise ValueError('Bundle entries must be regular files')
        if digest(bundle / name) != data['files'][name]:
            raise ValueError('Signed bundle file differs: ' + name)
    metadata = json.loads((bundle / 'manifest.json').read_text())
    if (metadata['image_sha256'] != data['files']['a6-wifi.img3'] or
            metadata['sha256'] != data['files']['modules.tar.gz'] or
            not metadata.get('boot_defaults') or not metadata.get('hardening')):
        raise ValueError('Module metadata disagrees with signed boot bundle')
    expected = ''.join(data['files'][name] + '  ' + name + '\n'
                       for name in ('a6-wifi.img3', 'a6-desktop.squashfs'))
    if (bundle / 'manifest.sha256').read_text() != expected:
        raise ValueError('On-phone manifest disagrees with bundle')
    subprocess.run(['openssl', 'pkeyutl', '-verify', '-rawin', '-pubin', '-inkey', str(PUBLIC),
                    '-in', str(bundle / 'manifest.sha256'), '-sigfile', str(bundle / 'manifest.sig')],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return data


def pack(output, browser=False, package=None, image=None, browser_image=None, desktop_image=None, apps=False):
    output = local(output)
    if apps and not browser: raise ValueError('App bundle requires the browser runtime')
    key = Path.home() / '.a6-update-signing.key'
    info = key.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise ValueError('Signing key must be user-owned regular mode600')
    package = local(package or ROOT / 'build/wifi-native')
    inner = local(ROOT / json.loads((package / 'signed-update.json').read_text())['directory'])
    sources = {'a6-wifi.img3': local(image or ROOT / 'build/arm/a6-wifi-brcmfmac.img3'),
               'a6-desktop.squashfs': local(desktop_image or ROOT / 'build/arch-bootstrap/arch-hyprland-user-desktop-native.squashfs'),
               **{name: package / name for name in ('modules.tar.gz', 'manifest.json', 'firewall-modules.json')},
               **{name: inner / name for name in ('manifest.sha256', 'manifest.sig')}}
    if browser:
        sources.update({'browser.squashfs': local(browser_image or ROOT / 'build/epiphany-runtime/browser.squashfs'),
                        'time-runtime.tar.gz': ROOT / 'build/time-runtime/runtime.tar.gz'})
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, source in sources.items():
        shutil.copyfile(source, output / name)
        (output / name).chmod(0o600)
    if desktop_image:
        # The isolated root changed; sign its exact inner image/root pair too.
        (output/'manifest.sha256').write_text(''.join(digest(output/name)+'  '+name+'\n' for name in ('a6-wifi.img3','a6-desktop.squashfs')))
        subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(key),'-in',str(output/'manifest.sha256'),'-out',str(output/'manifest.sig')],check=True)
    if apps:
        with tarfile.open(output/'app-helpers.tar.gz','w:gz') as archive:
            for name in APP_HELPERS:
                data=(ROOT/'rootfs'/name).read_bytes()
                entry=tarfile.TarInfo(name);entry.mode=0o600;entry.size=len(data)
                archive.addfile(entry,io.BytesIO(data))
        sources['app-helpers.tar.gz']=output/'app-helpers.tar.gz'
    if apps:
        import importlib.util
        spec=importlib.util.spec_from_file_location('bootstrap',ROOT/'scripts/prepare-a6-network-bootstrap.py')
        bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
        bootstrap.build(output/'modules.tar.gz',output/'network-bootstrap.tar.gz')
        sources['network-bootstrap.tar.gz']=output/'network-bootstrap.tar.gz'
    release = dict(format=4 if apps else (2 if browser else 1), files={name: digest(output / name) for name in sources})
    (output / 'release.json').write_text(json.dumps(release, sort_keys=True, indent=2) + '\n')
    subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(key),
                    '-in', str(output / 'release.json'), '-out', str(output / 'release.sig')], check=True)
    verify(output)
    print('Complete RAM boot bundle signed and verified, including modules and metadata.')


def apply(bundle):
    bundle = local(bundle)
    data = verify(bundle)
    state = ROOT / 'build/ram-updates'
    state.mkdir(mode=0o700, exist_ok=True)
    target = state / ('release-' + digest(bundle / 'release.json'))
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=state, prefix='stage-') as tmp:
            stage = Path(tmp) / 'bundle'
            stage.mkdir(mode=0o700)
            for name in (*data['files'], 'release.json', 'release.sig'):
                shutil.copyfile(bundle / name, stage / name)
                (stage / name).chmod(0o600)
            verify(stage)  # Verify the copied bytes before selection changes.
            (stage / 'signed-update.json').write_text(json.dumps({'directory': str(target.relative_to(ROOT))}) + '\n')
            stage.rename(target)
    verify(target)
    pointer = state / 'selection.json'
    previous = json.loads(pointer.read_text())['current'] if pointer.exists() else None
    if previous != str(target.relative_to(ROOT)):
        data = {'current': str(target.relative_to(ROOT)), 'previous': previous}
        fd, name = tempfile.mkstemp(dir=state, prefix='selection-')
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, pointer)
        finally:
            Path(name).unlink(missing_ok=True)
    print('Verified bundle selected for the next assisted RAM boot; live phone unchanged.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('pack', 'verify', 'apply'))
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--browser', action='store_true', help='Include signed Epiphany and NTS runtimes when packing')
    parser.add_argument('--package-dir', type=Path, help='Pack an isolated built module package')
    parser.add_argument('--image', type=Path, help='Pack its matching isolated image')
    parser.add_argument('--apps', action='store_true', help='Sign the app-service and browser RAM helpers too')
    parser.add_argument('--desktop-image', type=Path, help='Pack and sign an isolated desktop root')
    parser.add_argument('--browser-image', type=Path, help='Pack an isolated browser runtime image')
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == 'pack':
        pack(args.bundle, args.browser, args.package_dir, args.image, args.browser_image, args.desktop_image, args.apps)
    elif args.action == 'apply':
        apply(args.bundle)
    else:
        verify(args.bundle)
        print('Complete signed RAM bundle verification passed.')


if __name__ == '__main__':
    main()

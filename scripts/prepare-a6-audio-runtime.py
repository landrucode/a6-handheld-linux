#!/usr/bin/env python3
"""Prepare pinned signed ARM ALSA/PipeWire packages; no phone operations."""
import argparse
import hashlib
import json
import re
import posixpath
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = ROOT / 'build/arch-bootstrap'
    cache = archive / 'downloads'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop-libs', type=Path,
                        default=ROOT/'build/wifi-native/desktop-libs/graphics-runtime/usr/lib')
    args = parser.parse_args()
    pin = json.loads((ROOT/'rootfs/arch-audio-packages.json').read_text())
    mirror = pin['mirror']
    selected = pin['packages']
    output = ROOT / 'build/audio-alsa-runtime'
    runtime = output / 'runtime'
    import shutil
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, spec in sorted(selected.items()):
        filename = spec['filename']
        package = cache / filename
        for suffix in ('', '.sig'):
            dest = Path(str(package) + suffix)
            if not dest.exists():
                partial = Path(str(dest) + '.part')
                subprocess.run(['curl', '-fLsS', '--max-time', '60',
                                mirror + spec['repo'] + '/' + filename + suffix,
                                '-o', str(partial)], check=True)
                partial.replace(dest)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        if digest != spec['sha256']:
            raise RuntimeError('Package checksum mismatch: ' + name)
        verified = subprocess.run(
            ['gpg', '--homedir', str(archive / 'gnupg'), '--batch', '--status-fd', '1',
             '--verify', str(package) + '.sig', str(package)],
            capture_output=True, text=True, check=True)
        if not any(pin['signing_fingerprint'] in line.split()
                   for line in verified.stdout.splitlines()
                   if line.startswith('[GNUPG:] VALIDSIG ')):
            raise RuntimeError('Unexpected package signer: ' + name)
        with tarfile.open(package) as t:
            def safe_member(member, destination):
                if member.issym() and member.linkname.startswith('/'):
                    member = member.replace(linkname=posixpath.relpath(
                        member.linkname.lstrip('/'), posixpath.dirname(member.name)))
                return tarfile.data_filter(member, destination)
            t.extractall(runtime, filter=safe_member)
        manifest[name] = {'filename': filename, 'sha256': digest,
                          'version': spec['version']}
    # Resolve actual execution/plugin libraries against the pinned desktop.
    desktop = args.desktop_libs.resolve()
    if not desktop.is_relative_to(ROOT/'build') or not desktop.is_dir():
        raise ValueError('Expected generated desktop libraries under build/')
    queue = [runtime / 'usr/bin' / name for name in
             ('pipewire', 'pw-cli', 'pw-play', 'pw-record', 'wireplumber', 'dbus-run-session', 'dbus-daemon',
              'aplay', 'arecord', 'amixer')]
    config = (runtime / 'usr/share/pipewire/pipewire.conf').read_text()
    queue += [runtime / 'usr/lib/pipewire-0.3' / (name + '.so')
              for name in re.findall(r'name = (libpipewire-module-[a-z0-9-]+)', config)
              if (runtime / 'usr/lib/pipewire-0.3' / (name + '.so')).is_file()]
    for plugin in ('alsa', 'audioconvert', 'audiomixer', 'support', 'control'):
        queue += list((runtime / 'usr/lib/spa-0.2' / plugin).glob('*.so'))
    queue += list((runtime / 'usr/lib/wireplumber-0.5').glob('*.so'))
    seen = set()
    while queue:
        obj = queue.pop()
        if obj in seen:
            continue
        seen.add(obj)
        dynamic = subprocess.check_output(['llvm-readelf', '-d', str(obj)], text=True)
        for name in re.findall(r'Shared library: \[([^]]+)\]', dynamic):
            dest = runtime / 'usr/lib' / name
            if not dest.exists():
                source = desktop / name
                if not source.exists():
                    raise RuntimeError(f'Missing pinned ARM dependency {name} for {obj.name}')
                shutil.copy2(source.resolve(), dest)
            queue.append(dest)
    for directory in ('usr/include', 'usr/share/doc', 'usr/share/man', 'usr/share/locale'):
        shutil.rmtree(runtime / directory, ignore_errors=True)
    config = runtime / 'config'
    for kind in ('pipewire', 'wireplumber'):
        target = config / kind
        target.mkdir(parents=True, exist_ok=True)
        for conf in (runtime / 'usr/share' / kind).glob('*.conf'):
            shutil.copy2(conf, target)
        fragments = target / (kind + '.conf.d')
        fragments.mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'rootfs' / ('a6-audio-' + kind + '.conf'), fragments / '90-a6.conf')
    launchers = runtime / 'usr/local/bin'
    launchers.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'rootfs/a6-audio-session.sh', launchers / 'a6-audio-session')
    (launchers / 'a6-audio-session').chmod(0o755)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    subprocess.run(['tar', '-C', str(output), '-czf', str(output / 'runtime.tar.gz'),
                    'runtime', 'manifest.json'], check=True)
    print(f'Prepared {len(selected)} signed ARM audio packages in {output}')


if __name__ == '__main__':
    main()

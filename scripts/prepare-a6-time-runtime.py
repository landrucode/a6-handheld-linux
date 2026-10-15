#!/usr/bin/env python3
"""Prepare signature-verified ARM chrony for a RAM-only NTS client."""
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = ROOT / 'build/arch-bootstrap'
    cache = archive / 'downloads'
    mirror = json.loads((ROOT / 'rootfs/arch-tools-packages.json').read_text())['mirror']
    wanted = {'chrony', 'gnutls', 'nettle', 'libp11-kit', 'libtasn1',
              'libunistring', 'leancrypto', 'libidn2'}
    selected = {}
    output = ROOT / 'build/time-runtime'
    output.mkdir(parents=True, exist_ok=True)
    for repo in ('core', 'extra'):
        index = output / (repo + '.db')
        if not index.exists():
            subprocess.run(['curl', '-fLsS', '--max-time', '60',
                            mirror + repo + '/' + repo + '.db', '-o', str(index)], check=True)
        with tarfile.open(index) as db:
            for member in db:
                if not member.name.endswith('/desc'):
                    continue
                fields = {b.splitlines()[0].strip('%'): b.splitlines()[1:]
                          for b in db.extractfile(member).read().decode().split('\n\n') if b.strip()}
                name = fields.get('NAME', [''])[0]
                if name in wanted:
                    selected[name] = dict(repo=repo, filename=fields['FILENAME'][0],
                                          sha256=fields['SHA256SUM'][0], version=fields['VERSION'][0])
    if set(selected) != wanted:
        raise RuntimeError('Missing time packages: ' + str(wanted - set(selected)))
    runtime = output / 'runtime'
    if runtime.exists():
        raise RuntimeError('Preserve existing time runtime; choose a clean first preparation')
    runtime.mkdir(parents=True)
    for name, spec in sorted(selected.items()):
        package = cache / spec['filename']
        for suffix in ('', '.sig'):
            dest = Path(str(package) + suffix)
            if not dest.exists():
                partial = Path(str(dest) + '.part')
                subprocess.run(['curl', '-fLsS', '--max-time', '60',
                                mirror + spec['repo'] + '/' + spec['filename'] + suffix,
                                '-o', str(partial)], check=True)
                partial.replace(dest)
        if hashlib.file_digest(package.open('rb'), 'sha256').hexdigest() != spec['sha256']:
            raise RuntimeError('Time package checksum mismatch: ' + name)
        result = subprocess.run(['gpg', '--homedir', str(archive / 'gnupg'), '--batch',
                                 '--status-fd', '1', '--verify', str(package) + '.sig', str(package)],
                                capture_output=True, text=True, check=True)
        if '[GNUPG:] VALIDSIG ' not in result.stdout:
            raise RuntimeError('Time package signature missing: ' + name)
        with tarfile.open(package) as tar:
            def safe(member, destination):
                if member.issym() and member.linkname.startswith('/'):
                    member = member.replace(linkname=posixpath.relpath(
                        member.linkname.lstrip('/'), posixpath.dirname(member.name)))
                return tarfile.data_filter(member, destination)
            tar.extractall(runtime, filter=safe)
    desktop = ROOT / 'build/wifi-native/desktop-libs/graphics-runtime/usr/lib'
    shutil.copy2((desktop / 'ld-linux-armhf.so.3').resolve(),
                 runtime / 'usr/lib/ld-linux-armhf.so.3')
    queue = [runtime / 'usr/bin/chronyd', runtime / 'usr/bin/chronyc']
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
                    raise RuntimeError('Missing pinned time dependency: ' + name)
                shutil.copy2(source.resolve(), dest)
            queue.append(dest)
    for directory in ('usr/include', 'usr/share/man', 'usr/share/doc', 'usr/share/locale'):
        shutil.rmtree(runtime / directory, ignore_errors=True)
    chrony_symbols = subprocess.check_output(['llvm-readelf', '-Ws', str(runtime / 'usr/bin/chronyd')], text=True)
    tls_symbols = subprocess.check_output(['llvm-readelf', '-Ws', str(runtime / 'usr/lib/libgnutls.so.30')], text=True)
    adapter = 'clock_gettime@' in chrony_symbols and '__time64@' in tls_symbols
    if adapter:
        # Build against the signature-verified libc already pinned by the desktop.
        libc_spec = json.loads((ROOT / 'rootfs/arch-bootstrap-packages.json').read_text())['packages']['glibc']
        libc = cache / libc_spec['filename']
        if hashlib.file_digest(libc.open('rb'), 'sha256').hexdigest() != libc_spec['sha256']:
            raise RuntimeError('Pinned libc checksum mismatch')
        subprocess.run(['gpg', '--homedir', str(archive / 'gnupg'), '--batch', '--verify',
                        str(libc) + '.sig', str(libc)], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        sysroot = output / 'compiler-sysroot'
        sysroot.mkdir(exist_ok=False)
        with tarfile.open(libc) as tar:
            tar.extractall(sysroot, members=[m for m in tar if m.name.startswith(('usr/include/', 'usr/lib/'))],
                           filter='data')
        subprocess.run(['clang', '--target=arm-linux-gnueabihf', '-march=armv7-a', '-mfloat-abi=hard',
                        '--sysroot=' + str(sysroot), '-fuse-ld=lld', '-nostdlib', '-shared', '-fPIC',
                        '-O2', '-Wall', '-Wextra', '-Werror', str(ROOT / 'rootfs/a6-chrony-time64.c'),
                        '-L' + str(sysroot / 'usr/lib'), '-lc',
                        '-o', str(runtime / 'usr/lib/a6-chrony-time64.so')], check=True)
    elif not (('__clock_gettime64@' in chrony_symbols and '__time64@' in tls_symbols) or
              ('clock_gettime@' in chrony_symbols and ' time@' in tls_symbols)):
        raise RuntimeError('Unrecognised Chrony/GnuTLS time ABI; do not guess an adapter')
    config = runtime / 'config'
    config.mkdir()
    shutil.copy2(ROOT / 'rootfs/a6-chrony-nts.conf', config / 'chrony.conf')
    selected['_runtime'] = {'time64_adapter': adapter,
                            'config_sha256': hashlib.file_digest((config / 'chrony.conf').open('rb'), 'sha256').hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(selected, indent=2) + '\n')
    subprocess.run(['tar', '-C', str(output), '-czf', str(output / 'runtime.tar.gz'),
                    'runtime', 'manifest.json'], check=True)
    bundle = output / 'runtime.tar.gz'
    (output / 'runtime.sha256').write_text(hashlib.file_digest(bundle.open('rb'), 'sha256').hexdigest() + '\n')
    print('Signed ARM chrony runtime and ELF dependencies prepared.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Prepare signature-verified ARM tools for the unprivileged desktop."""
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build/user-tools'
RUNTIME = STAGE / 'runtime'
PIN = ROOT / 'rootfs/arch-user-tools-packages.json'
SIGNER = '68B3537F39A313B3E574D06777193F152BDBE6A6'
MIRROR = 'https://ca.us.mirror.archlinuxarm.org/armv7h/'
SEEDS = ('procps-ng', 'psmisc', 'iproute2', 'iputils', 'less', 'gawk',
         'tar', 'gzip', 'xz', 'unzip', 'which', 'file', 'curl', 'openssh',
         'ncurses', 'foot-terminfo', 'htop', 'tmux', 'brightnessctl', 'util-linux', 'p11-kit', 'libp11-kit', 'ca-certificates-mozilla')


# Ship commands the handheld needs, rather than every administrative utility.
COMMANDS = {
    'util-linux': {'lsblk', 'dmesg', 'setpriv'},
    'openssh': {'ssh', 'scp', 'sftp', 'ssh-keygen', 'ssh-agent', 'ssh-add', 'ssh-keyscan'},
    'p11-kit': {'trust'},
    'ncurses': set(),
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    STAGE.mkdir(exist_ok=True)
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir()
    packages = {}
    pinned = json.loads(PIN.read_text())['packages']
    for name, f in pinned.items():
        packages[name] = {'FILENAME': [f['filename']], 'SHA256SUM': [f['sha256']],
                          'repo': f['repo'], 'PROVIDES': f['provides'],
                          'DEPENDS': f['dependencies'], 'LICENSE': f['license'],
                          'URL': f['upstream']}
    providers = {name: 'glibc' for name in ('libc.so.6', 'libm.so.6', 'libdl.so.2', 'libpthread.so.0', 'librt.so.1', 'libresolv.so.2', 'ld-linux-armhf.so.3')}
    for name, f in packages.items():
        for provided in f.get('PROVIDES', []):
            match = re.fullmatch(r'(.+\.so)=([0-9.]+)-32', provided)
            if match:
                providers[match[1] + '.' + match[2]] = name
    providers.update({
        'libhunspell-1.7.so.0': 'hunspell', 'libtheoradec.so.2': 'libtheora', 'libtheoraenc.so.2': 'libtheora', 'libtheora.so.0': 'libtheora',
        'libSDL2-2.0.so.0': 'sdl2-compat', 'libtbb.so.12': 'onetbb',
        'libcdda_paranoia.so.0': 'cdparanoia', 'libcdda_interface.so.0': 'cdparanoia',
        'librrd.so.8': 'rrdtool', 'libjbig.so.2.1': 'jbigkit', 'libhwy.so.1': 'highway',
        'libglut.so.3': 'freeglut', 'libdw.so.1': 'libelf', 'libelf.so.1': 'libelf',
        'libLLVM.so.23.1': 'llvm-libs', 'libopenjp2.so.7': 'openjpeg2',
        'libwoff2dec.so.1.0.2': 'woff2', 'libwoff2common.so.1.0.2': 'woff2',
        'libhyphen.so.0': 'hyphen', 'libmanette-0.2.so.0': 'libmanette',
        'liblcms2.so.2': 'lcms2', 'libfftw3.so.3': 'fftw',
        'libOpenEXR-3_5.so.34': 'openexr', 'libMagickCore-7.Q16HDRI.so.10': 'imagemagick',
        'liblua5.1.so.5.1': 'lua51', 'liblmdb.so': 'lmdb', 'libOpenCL.so.1': 'ocl-icd',
        'libmp3lame.so.0': 'lame', 'libv4l2.so.0': 'v4l-utils', 'libzimg.so.2': 'zimg',
        'libzmq.so.5': 'zeromq', 'libgsm.so.1': 'gsm', 'librsvg-2.so.2': 'librsvg', 'libraw_r.so.25': 'libraw', 'libdb-6.2.so': 'db', 'liblastlog2.so.2': 'util-linux-libs',
    })
    manifest = {}

    extracted = set()

    def install(name, soname=None):
        key = (name, soname)
        if key in extracted:
            return
        extracted.add(key)
        f = packages[name]
        filename = f['FILENAME'][0]
        package = STAGE / filename
        for suffix in ('', '.sig'):
            target = Path(str(package) + suffix)
            if not target.exists():
                cached = next((p for directory in ('build/media-runtime', 'build/arch-bootstrap/downloads', 'build/audio-alsa-runtime/downloads')
                               if (p := ROOT / directory / (filename + suffix)).is_file()), None)
                if cached:
                    shutil.copyfile(cached, target)
                else:
                    partial = Path(str(target) + '.part')
                    subprocess.run(['curl', '-fLsS', '--max-time', '120',
                                    MIRROR + f['repo'] + '/' + filename + suffix,
                                    '-o', str(partial)], check=True)
                    partial.replace(target)
        if sha(package) != f['SHA256SUM'][0]:
            raise ValueError('User tool package hash differs: ' + name)
        result = subprocess.run(['gpg', '--homedir', str(ROOT / 'build/arch-bootstrap/gnupg'),
                                 '--batch', '--status-fd', '1', '--verify',
                                 str(package) + '.sig', str(package)], capture_output=True, text=True, check=True)
        if '[GNUPG:] VALIDSIG ' + SIGNER + ' ' not in result.stdout:
            raise ValueError('User tool package signer differs: ' + name)
        with tarfile.open(package) as archive:
            members = archive.getmembers()
            selected = set()
            if soname:
                by_name = {m.name: m for m in members}
                selected.update(m.name for m in members if m.name.startswith('usr/lib/') and posixpath.basename(m.name) == soname)
                pending = list(selected)
                while pending:
                    member = by_name[pending.pop()]
                    if member.issym() or member.islnk():
                        target = (posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
                                  if member.issym() else member.linkname)
                        target = target.lstrip('/')
                        if target in by_name and target not in selected:
                            selected.add(target)
                            pending.append(target)
                if name == 'glibc':
                    selected.update(m.name for m in members if m.name.startswith('usr/lib/gconv/') or posixpath.basename(m.name).startswith(('libnss_', 'ld-linux-')))
                if name == 'openssl':
                    selected.update(m.name for m in members if m.name.startswith('usr/lib/ossl-modules/'))
            for member in members:
                if soname and member.name not in selected:
                    continue
                if not member.name.startswith(('usr/bin/', 'usr/lib/', 'usr/share/file/', 'usr/share/terminfo/', 'usr/share/ca-certificates/', 'usr/share/p11-kit/')):
                    continue
                if name == 'ncurses' and member.name.startswith('usr/share/terminfo/') and not member.isdir():
                    if posixpath.basename(member.name) not in {'foot', 'foot-direct', 'tmux', 'tmux-256color', 'screen', 'screen-256color', 'xterm', 'xterm-256color', 'linux', 'vt100', 'dumb'}:
                        continue
                if member.name.startswith('usr/bin/'):
                    if name not in SEEDS or (name in COMMANDS and posixpath.basename(member.name) not in COMMANDS[name]):
                        continue
                if not soname and member.name.startswith('usr/lib/'):
                    # Resolve libraries from the selected commands, not unused package helpers.
                    if not (name == 'libp11-kit' and member.name.startswith('usr/lib/pkcs11/p11-kit-trust.so')):
                        continue
                if member.name.startswith(('usr/lib/ssh/sshd', 'usr/lib/systemd/', 'usr/lib/udev/')):
                    continue
                if member.name in ('usr/bin/su', 'usr/bin/sudo', 'usr/bin/doas', 'usr/bin/sshd'):
                    continue
                if member.name.startswith(('usr/include/', 'usr/share/man/', 'usr/share/doc/', 'usr/share/locale/', 'usr/lib/pkgconfig/', 'usr/lib/cmake/')) or member.name.endswith('.a'):
                    continue
                if member.issym() and member.linkname.startswith('/'):
                    member = member.replace(linkname=posixpath.relpath(member.linkname.lstrip('/'), posixpath.dirname(member.name)))
                archive.extract(member, RUNTIME, filter='data')
        manifest[name] = dict(filename=filename, sha256=sha(package), repo=f['repo'],
                              provides=f.get('PROVIDES', []), dependencies=f.get('DEPENDS', []),
                              license=f.get('LICENSE', []), upstream=f.get('URL', []))
        print('Verified user tool package:', name, flush=True)

    for name in SEEDS:
        install(name)
    seen = set()
    while True:
        queue = [p for p in RUNTIME.rglob('*') if p.is_file() and not p.is_symlink() and p not in seen]
        if not queue:
            break
        for obj in queue:
            seen.add(obj)
            with obj.open('rb') as stream:
                if stream.read(4) != b'\x7fELF':
                    continue
            if subprocess.check_output(['llvm-readelf', '-h', str(obj)], text=True).find('ARM') < 0:
                raise ValueError('Non-ARM binary in user tool runtime')
            dynamic = subprocess.check_output(['llvm-readelf', '-d', str(obj)], text=True)
            search = [RUNTIME / 'usr/lib', obj.parent]
            for value in re.findall(r'\((?:RUNPATH|RPATH)\).*?\[([^]]+)\]', dynamic):
                for directory in value.split(':'):
                    if '$ORIGIN' in directory or '${ORIGIN}' in directory:
                        search.append(Path(directory.replace('${ORIGIN}', str(obj.parent)).replace('$ORIGIN', str(obj.parent))))
                    elif directory.startswith('/usr/lib'):
                        search.append(RUNTIME / directory.lstrip('/'))
            def supplied(soname):
                return any((directory / soname).exists() for directory in search)
            for soname in re.findall(r'Shared library: \[([^]]+)\]', dynamic):
                if '/' in soname:
                    raise ValueError('Unexpected absolute ELF dependency: ' + soname)
                if supplied(soname):
                    continue
                if soname in providers:
                    install(providers[soname], soname)
                elif soname.startswith('libxcb-'):
                    install('libxcb', soname)
                else:
                    candidates = (soname.split('.so')[0], soname.split('.so')[0].lower(), soname.split('.so')[0].lower().removeprefix('lib'))
                    name = next((n for n in candidates if n in packages), None)
                    if name is None:
                        raise ValueError('Unresolved user tool library: ' + soname)
                    install(name, soname)
                if not supplied(soname):
                    raise ValueError('Provider did not supply ' + soname)
    if not (RUNTIME / 'lib').exists():
        (RUNTIME / 'lib').symlink_to('usr/lib')

    # The runtime loader and bwrap must be executable by UID1000; never
    # carry package setuid bits into this diagnostic image.
    RUNTIME.chmod(0o755)
    for path in RUNTIME.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    (STAGE/'packages.json').write_text(json.dumps(dict(mirror=MIRROR, signing_fingerprint=SIGNER, packages=manifest), indent=2) + '\n')
    print('Verified user tool runtime:', sum(p.stat().st_size for p in RUNTIME.rglob('*') if p.is_file() and not p.is_symlink()), 'uncompressed bytes')


if __name__ == '__main__':
    main()

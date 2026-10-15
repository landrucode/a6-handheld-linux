#!/usr/bin/env python3
"""Prepare a signature-verified ARM Epiphany, our sole shipping browser."""
import argparse
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build/epiphany-runtime'
RUNTIME = STAGE / 'runtime'
PIN = ROOT / 'rootfs/arch-browser-packages.json'
SIGNER = '68B3537F39A313B3E574D06777193F152BDBE6A6'
MIRROR = 'https://ca.us.mirror.archlinuxarm.org/armv7h/'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sign', action='store_true', help='Sign with the private host key after building')
    args = parser.parse_args()
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
        'libzmq.so.5': 'zeromq', 'libgsm.so.1': 'gsm', 'librsvg-2.so.2': 'librsvg', 'libraw_r.so.25': 'libraw', 'libImath-3_2.so.30': 'imath', 'libpython3.14.so.1.0': 'python', 'libQt6Core.so.6': 'qt6-base', 'libQt6Gui.so.6': 'qt6-base', 'libQt6Widgets.so.6': 'qt6-base', 'libQt6Svg.so.6': 'qt6-svg', 'libdb-6.2.so': 'db', 'libX11-xcb.so.1': 'libx11', 'libpxbackend-1.0.so': 'libproxy', 'libgbm.so.1': 'mesa', 'libEGL.so.1': 'libglvnd', 'libGL.so.1': 'libglvnd', 'libGLESv2.so.2': 'libglvnd', 'libOpenGL.so.0': 'libglvnd', 'libGLdispatch.so.0': 'libglvnd', 'libGLX.so.0': 'libglvnd',
    })
    # These packages do not advertise every versioned GStreamer soname.
    for name, components in (
        ('gstreamer', 'base check controller net reamer'),
        ('gst-plugins-base-libs', 'allocators app audio fft gl pbutils riff rtp rtsp sdp tag video'),
        ('gst-plugins-bad-libs', 'adaptivedemux analytics badaudio basecamerabinsrc codecparsers codecs cuda dxva insertbin isoff mpegts mse photography play player sctp uridownloader va vulkan wayland webrtc webrtcnice')):
        for component in components.split():
            providers['libgst' + component + '-1.0.so.0'] = name
    providers['libgstreamer-1.0.so.0'] = 'gstreamer'
    for name in ('gstreamer', 'gst-plugins-base-libs', 'gst-plugins-bad-libs'):
        archive = STAGE / packages[name]['FILENAME'][0]
        if not archive.exists():
            continue
        with tarfile.open(archive) as stream:
            for member in stream:
                if member.name.startswith('usr/lib/') and member.name.count('/') == 2 and '.so.' in member.name:
                    providers[posixpath.basename(member.name)] = name

    manifest = {}
    extracted = set()
    seed_names = ('epiphany', 'webkitgtk-6.0', 'gtk4', 'libadwaita', 'bubblewrap',
                  'xdg-dbus-proxy', 'dbus', 'glib-networking', 'gsettings-desktop-schemas',
                  'iso-codes', 'gsettings-system-schemas', 'dconf', 'gdk-pixbuf2', 'hicolor-icon-theme',
                  'adwaita-icon-theme', 'gstreamer', 'gst-plugins-base', 'glycin', 'glib2-devel')
    bins = {'epiphany', 'bwrap', 'xdg-dbus-proxy', 'dbus-daemon', 'dbus-run-session'}

    def install(name, soname=None):
        if (name, soname) in extracted:
            return
        extracted.add((name, soname))
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
            raise ValueError('Epiphany package hash differs: ' + name)
        result = subprocess.run(['gpg', '--homedir', str(ROOT / 'build/arch-bootstrap/gnupg'),
                                 '--batch', '--status-fd', '1', '--verify',
                                 str(package) + '.sig', str(package)], capture_output=True, text=True, check=True)
        if '[GNUPG:] VALIDSIG ' + SIGNER + ' ' not in result.stdout:
            raise ValueError('Epiphany package signer differs: ' + name)
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
                                  if member.issym() else member.linkname).lstrip('/')
                        if target in by_name and target not in selected:
                            selected.add(target)
                            pending.append(target)
                if name == 'glibc':
                    selected.update(m.name for m in members if m.name.startswith('usr/lib/gconv/') or posixpath.basename(m.name).startswith(('libnss_', 'ld-linux-')))
                if name == 'openssl':
                    selected.update(m.name for m in members if m.name.startswith('usr/lib/ossl-modules/'))
            for member in members:
                if name == 'glib2-devel' and member.name == 'usr/bin/glib-mkenums':
                    (STAGE / 'glib-mkenums').write_bytes(archive.extractfile(member).read())
                    continue
                if name == 'gsettings-desktop-schemas' and member.name == 'usr/include/gsettings-desktop-schemas/gdesktop-enums.h':
                    (STAGE / 'gdesktop-enums.h').write_bytes(archive.extractfile(member).read())
                    continue
                if soname and member.name not in selected:
                    continue
                if not soname and member.name.startswith('usr/bin/') and posixpath.basename(member.name) not in bins:
                    continue
                if not soname and member.name.startswith('usr/lib/'):
                    if not member.name.startswith(('usr/lib/webkitgtk-6.0/', 'usr/lib/epiphany/', 'usr/lib/gio/modules/', 'usr/lib/gtk-4.0/', 'usr/lib/gdk-pixbuf-2.0/', 'usr/lib/glycin-loaders/', 'usr/lib/gstreamer-1.0/', 'usr/lib/dconf/')):
                        continue
                if not member.name.startswith(('usr/bin/', 'usr/lib/', 'usr/share/')):
                    continue
                if member.name.startswith(('usr/include/', 'usr/share/man/', 'usr/share/doc/', 'usr/share/locale/', 'usr/lib/pkgconfig/', 'usr/lib/cmake/')) or member.name.endswith('.a'):
                    continue
                if member.name in ('usr/bin/su', 'usr/bin/sudo', 'usr/bin/doas', 'usr/bin/sshd'):
                    continue
                if member.issym() and member.linkname.startswith('/'):
                    member = member.replace(linkname=posixpath.relpath(member.linkname.lstrip('/'), posixpath.dirname(member.name)))
                archive.extract(member, RUNTIME, filter='data')
        manifest[name] = dict(filename=filename, sha256=sha(package), repo=f['repo'],
                              provides=f.get('PROVIDES', []), dependencies=f.get('DEPENDS', []),
                              license=f.get('LICENSE', []), upstream=f.get('URL', []))
        print('Verified Epiphany package:', name, flush=True)

    # Extract runtime modules and data only from browser components. Resolve
    # ordinary shared libraries individually, avoiding unrelated package tools.
    for name in seed_names:
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
                raise ValueError('Non-ARM binary in Epiphany image')
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
                        raise ValueError('Unresolved Epiphany library: ' + soname)
                    install(name, soname)
                if not supplied(soname):
                    raise ValueError('Provider did not supply ' + soname)
    if not (RUNTIME / 'lib').exists():
        (RUNTIME / 'lib').symlink_to('usr/lib')
    # Arch generates the desktop enum schema during installation. Generate it
    # with the verified GLib tool and matching verified GNOME header here.
    enums = subprocess.check_output(['python3', str(STAGE / 'glib-mkenums'),
        '--comments', '<!-- @comment@ -->', '--fhead', '<schemalist>',
        '--vhead', '<@type@ id="org.gnome.desktop.@EnumName@">',
        '--vprod', '<value nick="@valuenick@" value="@valuenum@"/>',
        '--vtail', '</@type@>', '--ftail', '</schemalist>', str(STAGE / 'gdesktop-enums.h')])
    (RUNTIME / 'usr/share/glib-2.0/schemas/org.gnome.desktop.enums.xml').write_bytes(enums)
    (RUNTIME / 'usr/share/glib-2.0/schemas/a6-software-rendering.gschema.override').write_text("[org.gnome.Epiphany.web]\nhardware-acceleration-policy='never'\n")
    subprocess.run(['glib-compile-schemas', '--strict', str(RUNTIME / 'usr/share/glib-2.0/schemas')], check=True)
    for name in ('su', 'sudo', 'doas', 'sshd'):
        (RUNTIME / 'usr/bin' / name).unlink(missing_ok=True)

    # The runtime loader and bwrap must be executable by UID1000; never
    # carry package setuid bits into this browser image.
    RUNTIME.chmod(0o755)
    for path in RUNTIME.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    (STAGE/'packages.json').write_text(json.dumps(dict(mirror=MIRROR, signing_fingerprint=SIGNER, packages=manifest), indent=2) + '\n')
    image = STAGE / 'browser.squashfs'
    if image.exists():
        raise ValueError('Preserve completed browser image; choose a fresh build directory')
    subprocess.run([str(ROOT / '.deps/squashfs-tools-4.7.2/squashfs-tools/mksquashfs'),
                    str(RUNTIME), str(image), '-noappend', '-all-root', '-root-mode', '0755', '-no-xattrs', '-comp', 'zstd',
                    '-Xcompression-level', '3', '-b', '131072', '-repro-time', '0', '-processors', '2', '-no-progress'], check=True)
    manifest_path = STAGE / 'browser.sha256'
    manifest_path.write_text(sha(image) + '  browser.squashfs\n')
    if args.sign:
        key = Path.home() / '.a6-update-signing.key'
        info = key.lstat()
        import os, stat
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            raise ValueError('Signing key ownership/mode differs')
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(key),
                        '-in', str(manifest_path), '-out', str(STAGE / 'browser.sig')], check=True)
        subprocess.run(['openssl', 'pkeyutl', '-verify', '-rawin', '-pubin', '-inkey', str(ROOT / 'build/wifi-boot-assets/update-public.pem'),
                        '-in', str(manifest_path), '-sigfile', str(STAGE / 'browser.sig')], check=True)
    print('Epiphany runtime built from pinned signed packages:', image.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()

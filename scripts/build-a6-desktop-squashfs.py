#!/usr/bin/env python3
"""Build and round-trip a pinned desktop SquashFS on the host, without phone access."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '3672e590d95045e65419ad03c11706dc4446638d12e6388de36265a68c49ffad'
TOOLS_COMMIT = '99d23a31b471433c51e9c145aeba2ab1536e34df'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', action='store_true', help='use the pinned native-touch desktop bundle')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'build/arch-bootstrap/arch-hyprland-user-desktop.squashfs')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('output already exists; use a different --output for a repeat')
    stem = 'arch-hyprland-user-desktop-native' if args.native else 'arch-hyprland-user-desktop'
    expected_source = ('05e935c757ac8b67604e6e17f00341947407712893bd07d9411e05773f7cecf6'
                       if args.native else SOURCE_SHA)
    source = ROOT / 'build/arch-bootstrap' / (stem + '.tar.gz')
    if digest(source) != expected_source:
        raise ValueError('unexpected desktop archive')
    tools = ROOT / '.deps/squashfs-tools-4.7.2'
    commit = subprocess.check_output(['git', '-C', str(tools), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != TOOLS_COMMIT:
        raise ValueError('unexpected SquashFS tools source')
    maker, reader = [tools / 'squashfs-tools' / name for name in ('mksquashfs', 'unsquashfs')]
    with tarfile.open(source) as archive:
        members = archive.getmembers()
    for member in members:
        if member.name.startswith('/') or '..' in Path(member.name).parts:
            raise ValueError('unsafe archive path')
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ValueError('unexpected special file')
        if (member.uid, member.gid) != (0, 0):
            raise ValueError('unexpected archive ownership')
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(maker), '-', str(output), '-tar', '-no-strip', '-noappend',
               '-comp', 'zstd', '-Xcompression-level', '15', '-b', '131072',
               '-repro-time', '0', '-all-root', '-root-mode', '0755',
               '-no-xattrs', '-processors', '2',
               '-mem', '256M', '-no-progress']
    with output.with_suffix('.build.log').open('w') as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
        try:
            with gzip.open(source, 'rb') as archive:
                shutil.copyfileobj(archive, process.stdin, length=1024 * 1024)
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError('mksquashfs failed; see build log')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    manifest = ROOT / 'build/arch-bootstrap' / (stem + '-files.sha256')
    hashes = dict(line.split('  ', 1)[::-1] for line in manifest.read_text().splitlines())
    if len(hashes) != 1135:
        raise ValueError('unexpected manifest count')
    listing = subprocess.check_output([str(reader), '-lln', str(output)], text=True)
    lines = listing.splitlines()
    if not lines or not lines[0].startswith('drwxr-xr-x 0/0 '):
        raise ValueError('incorrect generated root permissions/ownership')
    if any(line.split()[1] != '0/0' for line in lines):
        raise ValueError('non-root image ownership')
    with tempfile.TemporaryDirectory(prefix='a6-squashfs-check-', dir=output.parent) as tmp:
        unpacked = Path(tmp) / 'root'
        result = subprocess.run([str(reader), '-no-progress', '-processors', '2',
                                 '-d', str(unpacked), str(output)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output.with_suffix('.roundtrip.log').write_text(result.stdout)
        if result.returncode:
            raise RuntimeError('unsquashfs failed; see roundtrip log')
        checked = 0
        for member in members:
            path = unpacked / member.name
            info = path.lstat()
            if stat.S_IMODE(info.st_mode) != member.mode:
                raise ValueError('mode changed: ' + member.name)
            if member.issym():
                if not stat.S_ISLNK(info.st_mode) or os.readlink(path) != member.linkname:
                    raise ValueError('symlink changed: ' + member.name)
            elif member.isdir():
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError('directory changed: ' + member.name)
            elif member.isfile():
                name = str(Path(member.name).relative_to('graphics-runtime'))
                if not stat.S_ISREG(info.st_mode) or digest(path) != hashes[name]:
                    raise ValueError('payload changed: ' + member.name)
                checked += 1
            else:
                if not os.path.samefile(path, unpacked / member.linkname):
                    raise ValueError('hardlink changed: ' + member.name)
        if checked != len(hashes):
            raise ValueError('regular-file count changed')
    payload = sum(member.size for member in members if member.isfile())
    size = output.stat().st_size
    report = {'source_sha256': expected_source, 'source_archive_bytes': source.stat().st_size,
              'source_regular_file_bytes': payload, 'source_members': len(members),
              'verified_regular_files': checked, 'squashfs_bytes': size,
              'squashfs_sha256': digest(output), 'tools_commit': commit,
              'compression': 'zstd level 15, 128 KiB blocks', 'timestamps': 0,
              'ownership': 'all root:root; generated root mode 0755',
              'file_payload_minus_image_bytes': payload - size,
              'phone_tested': False,
              'limitation': 'Savings exclude page cache, writable overlay and filesystem metadata; not measured MemAvailable.'}
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Verify a signed desktop's tools in Foot on a live RAM boot, over USB control."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import shlex
import shutil
import tempfile
import os
import hashlib
import time

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--resume', action='store_true', help='Resume the exact existing diagnostic image, checking its prefix')
    parser.add_argument('--acm-broker', type=Path, help='Use an explicitly selected persistent USB ACM broker for control')
    args = parser.parse_args()
    update = load('update', 'manage-a6-ram-update.py')
    release = update.verify(args.bundle)
    # Send only the added tools for this live diagnostic; the complete shipping
    # desktop is separately signed and verified above. The existing desktop
    # supplies Foot and its unchanged graphics libraries.
    source = ROOT / 'build/user-tools/verification.squashfs'
    if not args.resume:
        source.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/user-tools') as temporary:
            tree = Path(temporary) / 'graphics-runtime'
            shutil.copytree(ROOT / 'build/user-tools/runtime/usr', tree / 'usr', symlinks=True)
            (tree / 'etc/ssl').mkdir(parents=True)
            (tree / 'usr/local/bin').mkdir(parents=True)
            for name in ('a6-prepare-user-desktop', 'a6-user-tools-check'):
                target = tree / 'usr/local/bin' / name
                shutil.copyfile(ROOT / 'rootfs' / (name + '.sh'), target)
                target.chmod(0o755)
            for directory in (Path(temporary), tree, tree / 'etc', tree / 'etc/ssl'):
                directory.chmod(0o755)
            subprocess.run([str(ROOT / '.deps/squashfs-tools-4.7.2/squashfs-tools/mksquashfs'),
                            temporary, str(source), '-noappend', '-all-root', '-root-mode', '0755',
                            '-no-xattrs', '-comp', 'zstd', '-Xcompression-level', '15', '-b', '131072',
                            '-processors', '2', '-no-progress'], check=True, stdout=subprocess.DEVNULL)
    rpc = load('rpc', 'a6-usb-http-rpc.py')
    phone = load('connection', 'a6-wifi-connect.py').Phone()
    def serial(command, timeout=20):
        rc, output = rpc.execute(command, Path.home() / '.a6-usb-rpc.token', timeout)
        return subprocess.CompletedProcess([], rc, output + '\n', '')
    if args.acm_broker:
        os.environ.pop('A6_USB_HTTP_RPC_TOKEN', None)
        os.environ['A6_ACM_BROKER'] = str(args.acm_broker.resolve())
    else:
        phone.collector.serial = serial
    checked = phone.checked
    phone.checked = lambda command, timeout=20: checked('busybox sh -e -c ' + shlex.quote(command), timeout)
    try:
        phone.checked('test -S /tmp/graphics-runtime/run/user/1000/wayland-1; test ! -e /tmp/a6-user-tools-base; test ! -e /tmp/a6-user-tools-root')
        # Close the browser before holding a second compressed root in RAM.
        phone.checked('if test -w /tmp/a6-cgroup/browser/cgroup.kill; then echo 1 >/tmp/a6-cgroup/browser/cgroup.kill; fi')
        provision = load('provision', 'a6-provision-boot.py')
        transport, reason = provision.choose_image_transport(phone)
        print('Tool verification image_transport=' + transport + ' reason=' + reason, flush=True)
        with source.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        destination = '/tmp/user-tools-test.squashfs'
        provision.deliver_image(phone, transport, source, destination, digest, resume=args.resume)
        manifest = ROOT / 'build/user-tools/desktop-test.sha256'
        signature = manifest.with_suffix('.sig')
        manifest.write_text(digest + '  user-tools-test.squashfs\n')
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(Path.home() / '.a6-update-signing.key'), '-in', str(manifest), '-out', str(signature)], check=True)
        phone.upload(manifest.read_bytes(), '/tmp/user-tools-test.sha256')
        phone.upload(signature.read_bytes(), '/tmp/user-tools-test.sig')
        phone.checked('cd /tmp; /tmp/a6-native/tools/usr/lib/ld-linux-armhf.so.3 --library-path /tmp/a6-native/tools/usr/lib /tmp/a6-native/tools/usr/bin/openssl pkeyutl -verify -rawin -pubin -inkey /etc/a6-update-public.pem -in user-tools-test.sha256 -sigfile user-tools-test.sig >/dev/null; busybox sha256sum -c user-tools-test.sha256', timeout=40)
        phone.checked('busybox mkdir /tmp/a6-user-tools-base /tmp/a6-user-tools-state /tmp/a6-user-tools-root; busybox mount -t squashfs -o loop,ro /tmp/user-tools-test.squashfs /tmp/a6-user-tools-base; busybox mount -t tmpfs -o size=32m,mode=0700,nosuid,nodev tmpfs /tmp/a6-user-tools-state; busybox mkdir /tmp/a6-user-tools-state/upper /tmp/a6-user-tools-state/work; busybox mount -t overlay overlay -o lowerdir=/tmp/a6-user-tools-base/graphics-runtime:/tmp/a6-desktop-base/graphics-runtime,upperdir=/tmp/a6-user-tools-state/upper,workdir=/tmp/a6-user-tools-state/work /tmp/a6-user-tools-root')
        phone.checked('root=/tmp/a6-user-tools-root; busybox chmod 755 "$root"; for name in dev proc; do busybox mount --bind /$name "$root/$name"; done; busybox mount --bind /dev/pts "$root/dev/pts"; busybox mount -t sysfs -o ro sysfs "$root/sys"; for name in run home; do busybox mount --bind /tmp/graphics-runtime/$name "$root/$name"; done; busybox cp /etc/resolv.conf "$root/etc/resolv.conf"; busybox chmod 644 "$root/etc/resolv.conf"; for name in sudo su doas sshd; do busybox rm -f "$root/usr/bin/$name" "$root/usr/sbin/$name"; done; busybox chroot "$root" /bin/bash /usr/local/bin/a6-prepare-user-desktop', timeout=40)
        phone.checked("busybox setsid busybox chroot /tmp/a6-user-tools-root /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 /usr/bin/foot --app-id=a6-tools-check /usr/local/bin/a6-user-tools-check </dev/null >/tmp/a6-user-tools-foot.private.log 2>&1 & echo $! >/tmp/a6-user-tools-foot.pid")
        for _ in range(45):
            out = phone.checked('if test -r /tmp/graphics-runtime/home/a6/user-tools-check.results; then busybox cat /tmp/graphics-runtime/home/a6/user-tools-check.results; fi')
            if 'brightness' in out:
                for line in out.splitlines():
                    if line.startswith(('PASS ', 'FAIL ', 'BLOCKED ')):
                        print(line)
                break
            time.sleep(1)
        else:
            raise RuntimeError('Foot checks did not complete; private evidence retained')
    finally:
        evidence = ROOT / 'build/session-logs' / ('user-tools-' + str(time.time_ns()) + '.private.log')
        evidence.write_text('\n'.join(phone.evidence))
        evidence.chmod(0o600)


if __name__ == '__main__':
    main()

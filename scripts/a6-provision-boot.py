#!/usr/bin/env python3
"""Provision a RAM boot: USB bootstrap/control, Wi-Fi large-image delivery.

No association trial, credential logging, NAND, reset or automatic exploit.
Only network bootstrap and firmware arrive before HSIC starts. Credentials never
enter an image or bundle; the phone removes their RAM file after loading WPA.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import sys
import time
import tarfile
ROOT=Path(__file__).resolve().parents[1]

class UploadTransportError(RuntimeError):
    """A bulk socket failed; the owned receiver has been stopped."""

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def validate_candidate_directory(candidate, selected=None):
    if not candidate.is_relative_to(ROOT/'build/signed-updates') and candidate != selected:
        raise ValueError('Signed candidate outside private build/')

def upload_large(phone,path,destination,resume=False):
    try:
        return upload_large_once(phone,path,destination,resume)
    except UploadTransportError:
        if getattr(phone,'usb_upload_recovery_used',False):raise
        # One recovery per provisioning invocation, before radio/desktop startup.
        # ACM control remains available; only Ethernet bulk endpoints are cycled.
        phone.usb_upload_recovery_used=True
        phone.checked('test ! -e /tmp/a6-connection.connected && '
                      'test ! -e /tmp/a6-wifi-boot.ready && '
                      'test ! -d /sys/class/net/wlan0 && '
                      'if test -f /etc/a6-usb-upload-recover.sh; then '
                      'sh /etc/a6-usb-upload-recover.sh; else '
                      'busybox ip link set usb0 down && busybox ip link set usb0 up; fi')
        return upload_large_once(phone,path,destination,True)

def upload_large_once(phone,path,destination,resume=False):
    with path.open('rb') as source:
        digest=hashlib.file_digest(source,'sha256').hexdigest()
    offset=0
    if resume:
        existing=phone.serial('if test -f '+destination+'; then busybox sha256sum '+destination+'; fi')
        if re.search(r'(?m)^'+digest+r'\s+'+re.escape(destination)+r'$',existing):
            return digest+'  '+destination.lstrip('/')
        if re.search(r'(?m)^[0-9a-f]{64}\s+'+re.escape(destination)+r'$',existing):
            raise ValueError('Completed RAM file differs; preserve it for investigation')
        partial=phone.serial('if test -f '+destination+'.part; then busybox stat -c "PART_BYTES=%s" '+destination+'.part; busybox sha256sum '+destination+'.part; fi')
        size=re.search(r'(?m)^PART_BYTES=(\d+)$',partial)
        if size:
            offset=int(size[1])
            if offset>path.stat().st_size:raise ValueError('RAM partial exceeds local source')
            prefix=hashlib.sha256()
            with path.open('rb') as source:
                remaining=offset
                while remaining:
                    chunk=source.read(min(1048576,remaining))
                    if not chunk:raise ValueError('Local source truncated during prefix verification')
                    prefix.update(chunk);remaining-=len(chunk)
            if not re.search(r'(?m)^'+prefix.hexdigest()+r'\s+'+re.escape(destination+'.part')+r'$',partial):
                raise ValueError('RAM partial differs from exact source prefix')
        phone.checked('! (busybox netstat -lnt 2>/dev/null | busybox grep -q ":8083 ")')
    # Short TCP windows avoid keeping gadget bulk endpoints busy continuously.
    # Only the final full-file digest publishes the staged file.
    while offset < path.stat().st_size:
        end=min(offset+getattr(phone,'upload_window_bytes',8*1024*1024),path.stat().st_size)
        stem='/tmp/a6-boot-upload-'+secrets.token_hex(4)
        worker='umask 077; echo $$ > '+stem+'.pid; busybox timeout 240 busybox nc -l -p 8083 192.168.7.2 '+('>> ' if offset else '> ')+destination+'.part; echo $? > '+stem+'.rc'
        phone.checked("busybox setsid busybox sh -c '"+worker+"' </dev/null >"+stem+'.log 2>&1 &')
        try:
            deadline=time.monotonic()+5
            while True:
                try:target=socket.create_connection(('192.168.7.2',8083),timeout=2);break
                except (ConnectionRefusedError,TimeoutError):
                    if time.monotonic()>deadline:raise
                    time.sleep(.1)
            with target,path.open('rb') as source:
                target.settimeout(20)
                source.seek(offset)
                remaining=end-offset
                while remaining:
                    data=source.read(min(65536,remaining))
                    if not data:raise ValueError('Local source truncated during upload')
                    target.sendall(data);remaining-=len(data)
                    time.sleep(len(data)/getattr(phone,'upload_rate_bytes',1024*1024))
                target.shutdown(socket.SHUT_WR)
        except OSError:
            # Unique setsid worker owns this process group. Stop it before hashing
            # the partial; never race a surviving writer or kill unrelated listeners.
            phone.checked('read pid < '+stem+'.pid; case "$pid" in '
                          "''|*[!0-9]*) exit 1;; esac; test \"$pid\" -gt 1 && "
                          'test "$(cat /proc/$pid/comm)" = busybox && '
                          'kill -TERM -"$pid" && sleep 1 && '
                          '! (busybox netstat -lnt 2>/dev/null | busybox grep -q ":8083 ")')
            raise UploadTransportError('USB bulk upload failed; verified partial preserved') from None
        phone.checked('sleep 1; test "$(cat '+stem+'.rc)" = 0 && test "$(busybox stat -c %s '+destination+'.part)" = '+str(end))
        offset=end
    phone.checked("printf '%s  %s\\n' "+digest+' '+destination+'.part | busybox sha256sum -c - && busybox mv '+destination+'.part '+destination,timeout=40)
    return digest+'  '+destination.lstrip('/')

def choose_image_transport(phone, seconds=60):
    """Require DHCP and a responding gateway within one bounded window."""
    deadline=time.monotonic()+seconds
    reason='dhcp_timeout'
    while time.monotonic()<deadline:
        remaining=deadline-time.monotonic()
        if remaining<4:break
        out=phone.checked(
            'if test ! -s /tmp/a6-connection.address; then echo A6_DHCP_PENDING; '
            'elif test ! -s /tmp/a6-connection.gateway; then echo A6_GATEWAY_FAILED; '
            'else read gateway < /tmp/a6-connection.gateway; '
            'if busybox timeout 2 busybox ping -I wlan0 -c 1 -W 1 "$gateway" '
            '>/tmp/a6-provision-gateway.private.log 2>&1; then echo A6_GATEWAY_READY; '
            'else echo A6_GATEWAY_FAILED; fi; fi', timeout=int(min(5,remaining)))
        lines=out.splitlines()
        if 'A6_GATEWAY_READY' in lines:return 'wifi','dhcp_and_gateway_ready'
        if 'A6_GATEWAY_FAILED' in lines:reason='gateway_unreachable'
        time.sleep(min(1,max(0,deadline-time.monotonic())))
    # Preserve the approximate sixty-second deadline even when the last probe
    # cannot safely fit. Never cycle USB or reset the radio on this path.
    time.sleep(max(0,deadline-time.monotonic()))
    return 'usb',reason

def prepare_browser_storage(phone):
    # Separate tmpfs avoids the fixed rootfs limit; it allocates only used bytes.
    phone.checked('busybox mkdir -p /tmp/a6-browser-images; if ! busybox grep -q " /tmp/a6-browser-images tmpfs " /proc/mounts; then test -z "$(busybox ls -A /tmp/a6-browser-images)"; busybox mount -t tmpfs -o size=192m,mode=0700,nosuid,nodev tmpfs /tmp/a6-browser-images; fi')


def deliver_image(phone, transport, source, destination, digest, resume=False):
    if destination == '/tmp/a6-browser-images/browser.squashfs':
        prepare_browser_storage(phone)
    if transport=='usb':
        phone.upload_window_bytes=1024*1024
        phone.upload_rate_bytes=256*1024
        return upload_large_once(phone,source,destination,resume)
    if transport!='wifi':raise ValueError('Unknown image transport')
    return module('wifi_images',ROOT/'scripts/a6-wifi-image-transfer.py').transfer(
        phone,source,destination,digest)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-dir',type=Path,default=ROOT/'build/wifi-native')
    parser.add_argument('--image',type=Path,default=ROOT/'build/arm/a6-wifi-brcmfmac.img3')
    parser.add_argument('--root',type=Path,default=ROOT/'build/arch-bootstrap/arch-hyprland-user-desktop-native.squashfs')
    parser.add_argument('--selected-update',action='store_true',help='Verify and provision the selected complete signed RAM bundle')
    parser.add_argument('--browser',action='store_true',help='Stage the signed Epiphany runtime over the selected image transport; do not launch it')
    parser.add_argument('--usb-images',action='store_true',help='Explicit legacy comparison: send large images over USB instead of Wi-Fi')
    parser.add_argument('--defer-browser',action='store_true',help='Stage signed browser helpers now; fetch and verify its image over Wi-Fi after startup')
    parser.add_argument('--nts',action='store_true',help='Stage and start the prepared authenticated time runtime after RAM provisioning')
    parser.add_argument('--resume',action='store_true',help='Reuse hash-verified RAM files and resume verified partial prefixes')
    parser.add_argument('--upload-window-mib',type=int,choices=range(1,9),default=8,help='Bound each USB TCP upload window (default: 8 MiB)')
    parser.add_argument('--upload-rate-kib',type=int,choices=(256,512,1024),default=1024,help='Pace USB uploads (default: 1024 KiB/s)')
    parser.add_argument('--validate-usb-recovery',action='store_true',help='Exercise the image guard once after uploads if no automatic recovery was needed')
    args=parser.parse_args()
    if args.defer_browser and not (args.browser and args.selected_update):
        parser.error('--defer-browser requires --browser --selected-update')
    if args.selected_update:
        selection=json.loads((ROOT/'build/ram-updates/selection.json').read_text())
        selected=(ROOT/selection['current']).resolve()
        updater=module('ram_update',ROOT/'scripts/manage-a6-ram-update.py')
        signed_release=updater.verify(selected)
        args.package_dir=selected
        args.image=selected/'a6-wifi.img3'
        args.root=selected/'a6-desktop.squashfs'
    if args.browser and (not args.selected_update or 'browser.squashfs' not in signed_release['files']):
        raise ValueError('Browser staging requires a selected format2 signed bundle')
    package_dir=args.package_dir.resolve()
    image=args.image.resolve()
    desktop_root=args.root.resolve()
    if not all(p.is_relative_to(ROOT/'build') for p in (package_dir,image,desktop_root)):
        raise ValueError('Boot candidate and package must be local build artifacts')
    os.environ.pop('A6_USB_HTTP_RPC_TOKEN',None)
    os.environ['A6_ACM_BROKER']=str(ROOT/'build/wifi-native/acm.sock')
    connection=module('connection',ROOT/'scripts/a6-wifi-connect.py');phone=connection.Phone()
    phone.upload_window_bytes=min(args.upload_window_mib,1)*1024*1024 if not args.usb_images else args.upload_window_mib*1024*1024
    phone.upload_rate_bytes=min(args.upload_rate_kib,256)*1024 if not args.usb_images else args.upload_rate_kib*1024
    manifest=json.loads((package_dir/'manifest.json').read_text())
    if not manifest.get('boot_defaults') or not manifest.get('hardening'):
        raise ValueError('Boot-defaults/hardened image package required')
    if hashlib.file_digest(image.open('rb'),'sha256').hexdigest()!=manifest['image_sha256']:
        raise ValueError('Image/package mismatch')
    config=Path.home()/'.a6-wifi.conf';info=config.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
        raise ValueError('Wi-Fi config must be user-owned regular mode600')
    private=config.read_bytes()
    if not 0<len(private)<=65536:raise ValueError('Configuration size refused')
    mac_file=Path.home()/'.a6-wifi-mac'
    if not mac_file.exists():
        data=bytearray(os.urandom(6));data[0]=(data[0]&0xfe)|0x02
        fd=os.open(mac_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(':'.join(f'{b:02x}' for b in data)+'\n')
    info=mac_file.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
        raise ValueError('Private MAC file ownership/mode invalid')
    mac=mac_file.read_bytes()
    if not re.fullmatch(rb'[0-9a-f]{2}(?::[0-9a-f]{2}){5}\n',mac) or int(mac[:2],16)&3!=2:
        raise ValueError('MAC must be locally administered unicast')
    try:
        phone.upload((ROOT/'rootfs/a6-power-longrun.sh').read_bytes(),'/tmp/a6-power-longrun.sh')
        phone.checked('busybox setsid busybox sh /tmp/a6-power-longrun.sh </dev/null >/tmp/a6-power-longrun-start.log 2>&1 &')
        phone.checked('test -f /etc/a6-wifi-boot.sh && test ! -e /tmp/a6-connection.connected && test ! -e /tmp/a6-wifi-boot.ready')
        # Refresh the reversible RAM helper so retained images support explicit
        # repeated recovery without inheriting the former once-per-boot marker.
        phone.upload((ROOT/'rootfs/a6-usb-upload-recover.sh').read_bytes(),'/etc/a6-usb-upload-recover.sh')
        package=package_dir/'modules.tar.gz'
        if hashlib.file_digest(package.open('rb'),'sha256').hexdigest()!=manifest['sha256']:raise ValueError('Native package mismatch')
        fw=json.loads((ROOT/'build/wifi-firmware/a6-download-package.json').read_text())
        firmware=(ROOT/fw['output']).resolve()
        if not firmware.is_relative_to(ROOT/'build/wifi-firmware') or hashlib.file_digest(firmware.open('rb'),'sha256').hexdigest()!=fw['sha256']:
            raise ValueError('Private firmware mismatch')
        signed=json.loads((package_dir/'signed-update.json').read_text())
        candidate=(ROOT/signed['directory']).resolve()
        validate_candidate_directory(candidate, selected if args.selected_update else None)
        import subprocess
        subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(ROOT/'build/wifi-boot-assets/update-public.pem'),'-in',str(candidate/'manifest.sha256'),'-sigfile',str(candidate/'manifest.sig')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        lines=(candidate/'manifest.sha256').read_text().splitlines()
        expected=[manifest['image_sha256']+'  a6-wifi.img3',hashlib.file_digest(desktop_root.open('rb'),'sha256').hexdigest()+'  a6-desktop.squashfs']
        if lines!=expected:raise ValueError('Signed candidate differs from boot assets')
        phone.checked('busybox mkdir -p /lib/firmware /tmp/a6-update.candidate')
        hashes=[]
        if not args.usb_images:
            # Replace the waiting retained-kernel worker explicitly; changing
            # its file does not change commands already buffered by its shell.
            phone.checked(r"""for f in /proc/[0-9]*/cmdline; do if busybox tr '\000' '\n' <"$f" | busybox grep -qx /etc/a6-wifi-boot.sh; then p=${f#/proc/}; p=${p%/cmdline}; kill -TERM "$p"; fi; done; busybox sleep 2""")
            phone.upload((ROOT/'rootfs/a6-wifi-boot.sh').read_bytes(),'/etc/a6-wifi-boot.sh')
            phone.checked('busybox touch /tmp/a6-network-bootstrap')
        bootstrap=selected/'network-bootstrap.tar.gz' if args.selected_update and signed_release['format']==4 and not args.usb_images else package
        initial=[(bootstrap,'/tmp/a6-native.tar.gz'),(firmware,'/lib/firmware/a6-centennial-tdk.trx')]
        if args.usb_images:initial.append((desktop_root,'/tmp/a6-desktop.squashfs'))
        for source,destination in initial:
            sender=upload_large if args.usb_images else upload_large_once
            hashes.append(sender(phone,source,destination,resume=args.resume))
        if args.browser:
            prepare_browser_storage(phone)
            subprocess.run(['bash', str(ROOT/'scripts/build-a6-pin-compressed-images.sh')], check=True)
            phone.upload((ROOT/'build/arm/a6-pin-compressed-images').read_bytes(), '/tmp/a6-pin-compressed-images')
            phone.checked('chmod 700 /tmp/a6-pin-compressed-images')
            if args.usb_images and not args.defer_browser:
                hashes.append(upload_large(phone,selected/'browser.squashfs','/tmp/a6-browser-images/browser.squashfs',resume=args.resume))
            if signed_release['format'] in (3,4):
                with tarfile.open(selected/'app-helpers.tar.gz') as archive:
                    entries=archive.getmembers()
                    names={m.name for m in entries}
                    allowed=set(updater.APP_HELPERS)
                    legacy=allowed-{'a6-wifi-boot.sh'}
                    variants=(allowed,allowed-{'a6-wifi-recover.sh','a6-wifi-health.sh','a6-wifi-off.sh'},legacy,legacy-{'a6-desktop-memory.sh','a6-release-boot-staging.sh','a6-desktop-workload-log.sh','a6-browser-state-watch.sh'},legacy-{'a6-mount-compressed-desktop.sh','a6-desktop-memory.sh','a6-release-boot-staging.sh','a6-desktop-workload-log.sh','a6-browser-state-watch.sh'})
                    if len(entries)!=len(names) or names not in variants:
                        raise ValueError('Unexpected signed app helper entries')
                    for member in entries:
                        if not member.isfile() or not 0<member.size<=16384:raise ValueError('Invalid app helper')
                        destination='/etc/'+member.name if member.name in ('a6-wifi-boot.sh','a6-wifi-off.sh','a6-start-native-desktop.sh','a6-mount-compressed-desktop.sh') else '/tmp/'+member.name
                        phone.upload(archive.extractfile(member).read(),destination)
            else:
                for name in ('a6-browser-memory-watch.sh','a6-launch-browser-test.sh','a6-browser-enter-root.sh','a6-browser-extra-swap.sh'):
                    phone.upload((ROOT/'rootfs'/name).read_bytes(),'/tmp/'+name)
        if args.usb_images:
            hashes.append(upload_large(phone,image,'/tmp/a6-update.candidate/a6-wifi.img3',resume=args.resume))
        # In the network path, defer the duplicate kernel verification copy
        # and its bootstrap digest until network startup. DFU boot used it already.
        if args.validate_usb_recovery and not getattr(phone,'usb_upload_recovery_used',False):
            phone.checked('test -f /etc/a6-usb-upload-recover.sh && sh /etc/a6-usb-upload-recover.sh')
            phone.usb_upload_recovery_used=True
            # Prove Ethernet carries data after the cycle without another large transfer.
            import urllib.request
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://192.168.7.2:8080/',timeout=5) as response:
                response.read(128)
            phone.checked('busybox sha256sum /tmp/a6-update.candidate/a6-wifi.img3 /tmp/a6-desktop.squashfs')
        # The root image was verified against the signed selected release.
        # Override the retained kernel's old native-desktop hash in RAM.
        if args.selected_update:
            phone.upload((hashlib.file_digest(args.root.open('rb'),'sha256').hexdigest()+'\n').encode(),'/etc/a6-boot/desktop.sha256')
        if args.usb_images:
            phone.checked('busybox ln /tmp/a6-desktop.squashfs /tmp/a6-update.candidate/a6-desktop.squashfs')
        for name in ('manifest.sha256','manifest.sig'):
            phone.upload((candidate/name).read_bytes(),'/tmp/a6-update.candidate/'+name)
        # Recovery service is USB-bound; token is injected only into RAM.
        token_path=Path.home()/'.a6-usb-rpc.token'
        if not token_path.exists():
            fd=os.open(token_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:stream.write(secrets.token_hex(32)+'\n')
        info=token_path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_uid!=os.getuid():
            raise ValueError('RPC token ownership/mode invalid')
        token=token_path.read_bytes()
        if not re.fullmatch(rb'[0-9a-f]{64}\n',token):raise ValueError('RPC token format invalid')
        phone.checked('busybox mkdir -p /www/cgi-bin; busybox chmod 0700 /www/cgi-bin')
        phone.upload((ROOT/'rootfs/a6-usb-rpc.cgi').read_bytes(),'/www/cgi-bin/a6-rpc.cgi')
        phone.upload(token,'/tmp/a6-usb-rpc.token',sensitive=True);del token
        for name in ('/etc/httpd.conf','/www/httpd.conf'):phone.upload(b'*.cgi:/bin/sh\n',name)
        phone.checked('busybox chmod 0700 /www/cgi-bin/a6-rpc.cgi; for f in /proc/[0-9]*/cmdline; do if busybox grep -q httpd "$f"; then p=${f#/proc/}; p=${p%/cmdline}; test "$p" = "$$" || kill -HUP "$p"; fi; done; true')
        modules=json.loads((package_dir/'firewall-modules.json').read_text())
        if any(not re.fullmatch(r'[a-z0-9_-]+',x) for x in modules):raise ValueError('Module names invalid')
        phone.upload((' '.join(modules)+'\n').encode(),'/tmp/a6-firewall.modules')
        phone.upload(('\n'.join(hashes)+'\n').encode(),'/tmp/a6-boot.sha256')
        phone.upload(mac,'/tmp/a6-boot.mac',sensitive=True)
        # Secret transfer echoes are discarded; no secret is bundled or logged.
        phone.upload(private,'/tmp/a6-wifi-boot.conf',sensitive=True);del private
        phone.upload((str(int(time.time()))+'\n').encode(),'/tmp/a6-boot.epoch')
        if not args.usb_images:
            phone.checked('busybox setsid busybox sh /etc/a6-wifi-boot.sh </dev/null >/tmp/a6-network-bootstrap.private.log 2>&1 &')
        phone.checked('busybox touch /tmp/a6-wifi-boot.ready')
        image_transport='usb' if args.usb_images else 'wifi'
        if not args.usb_images:
            print('Network bootstrap staged; checking DHCP and gateway for up to 60 seconds.',flush=True)
            image_transport,reason=choose_image_transport(phone)
            transport_log='image_transport='+image_transport+' reason='+reason
            print(transport_log,flush=True)
            phone.evidence.append(transport_log)
            phone.upload((transport_log+'\n').encode(),'/tmp/a6-image-transport.log')
            deliver_image(phone,image_transport,image,'/tmp/a6-update.candidate/a6-wifi.img3',manifest['image_sha256'],args.resume)
            hashes.append(manifest['image_sha256']+'  tmp/a6-update.candidate/a6-wifi.img3')
            phone.upload(('\n'.join(hashes)+'\n').encode(),'/tmp/a6-boot.sha256')
            deliver_image(phone,image_transport,package,'/tmp/a6-native-full.tar.gz',manifest['sha256'],args.resume)
            deliver_image(phone,image_transport,desktop_root,'/tmp/a6-desktop.squashfs',hashlib.file_digest(desktop_root.open('rb'),'sha256').hexdigest(),args.resume)
            if args.browser and (not args.defer_browser or image_transport=='usb'):
                deliver_image(phone,image_transport,selected/'browser.squashfs','/tmp/a6-browser-images/browser.squashfs',signed_release['files']['browser.squashfs'],args.resume)
            phone.checked('busybox ln /tmp/a6-desktop.squashfs /tmp/a6-update.candidate/a6-desktop.squashfs; busybox sh /etc/a6-verify-update.sh /tmp/a6-update.candidate',timeout=40)
            phone.checked('busybox tar -xzf /tmp/a6-native-full.tar.gz -C /tmp/a6-native; busybox rm /tmp/a6-native-full.tar.gz',timeout=40)
            phone.checked('busybox sh /etc/a6-mount-compressed-desktop.sh native',timeout=40)
            phone.checked('busybox cp /etc/resolv.conf /tmp/graphics-runtime/etc/resolv.conf; busybox chmod 644 /tmp/graphics-runtime/etc/resolv.conf')
            phone.checked('busybox rm /tmp/a6-network-bootstrap; busybox setsid busybox sh /etc/a6-start-native-desktop.sh </dev/null >/tmp/a6-desktop-launch.log 2>&1 &')
        if args.usb_images:
            transport_log='image_transport=usb reason=explicit_usb'
            phone.evidence.append(transport_log)
            phone.upload((transport_log+'\n').encode(),'/tmp/a6-image-transport.log')
        print('Signed RAM desktop staged and startup requested; large images used '+('USB.' if image_transport=='usb' else 'Wi-Fi.'))
        if args.nts:
            subprocess.run([sys.executable,str(ROOT/'scripts/a6-start-nts-time.py')]+(['--usb-images'] if image_transport=='usb' else [])+(['--selected-update'] if args.selected_update and 'time-runtime.tar.gz' in signed_release['files'] else []),check=True)
    finally:
        evidence=ROOT/'build/session-logs'/('wifi-boot-provision-'+secrets.token_hex(6)+'.private.log')
        fd=os.open(evidence,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write('\n'.join(phone.evidence))
if __name__=='__main__':main()

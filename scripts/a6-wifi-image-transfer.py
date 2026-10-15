#!/usr/bin/env python3
"""Send a hash-pinned RAM image over Wi-Fi; control stays on USB."""
import hashlib,ipaddress,json,secrets,socket,subprocess,time,re
from pathlib import PurePosixPath

def transfer(phone,source,destination,expected):
    if '..' in PurePosixPath(destination).parts or not destination.startswith('/tmp/') or any(c not in '/._-abcdefghijklmnopqrstuvwxyz0123456789' for c in destination):
        raise ValueError('Unexpected RAM image destination')
    with source.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise ValueError('Source image hash differs')
    existing=phone.checked('if test -f '+destination+'; then busybox sha256sum '+destination+'; fi')
    if expected+'  '+destination in existing:return
    if destination in existing:raise ValueError('Preserve differing completed RAM image')
    offset=0
    partial=phone.checked('if test -f '+destination+'.part; then busybox stat -c "PART_BYTES=%s" '+destination+'.part; busybox sha256sum '+destination+'.part; fi')
    size=re.search(r'(?m)^PART_BYTES=(\d+)$',partial)
    if size:
        offset=int(size[1])
        if offset>source.stat().st_size:raise ValueError('RAM image prefix too long')
        prefix=hashlib.sha256()
        with source.open('rb') as stream:
            remaining=offset
            while remaining:
                chunk=stream.read(min(1048576,remaining))
                if not chunk:raise ValueError('Source truncated during prefix check')
                prefix.update(chunk);remaining-=len(chunk)
        if not re.search(r'(?m)^'+prefix.hexdigest()+r'\s+'+re.escape(destination+'.part')+r'$',partial):
            raise ValueError('RAM image prefix differs; retained for inspection')
        if offset==source.stat().st_size:
            phone.checked('busybox mv '+destination+'.part '+destination)
            return

    out=phone.checked("busybox ip -4 -o addr show dev wlan0 | busybox awk '{print $4}'")
    addresses=[word for word in out.split() if '/' in word and word[0].isdigit()]
    address=str(ipaddress.IPv4Interface(addresses[-1]).ip)
    route=json.loads(subprocess.check_output(['ip','-j','route','get',address],text=True))[0]
    host=str(ipaddress.IPv4Address(route['prefsrc']))
    if not all(ipaddress.ip_address(x).is_private for x in (host,address)):raise ValueError('Expected private LAN peers')
    phone.checked('! (busybox netstat -lnt 2>/dev/null | busybox grep -q ":8085 ")')
    stem='/tmp/a6-image-'+secrets.token_hex(5)
    count=source.stat().st_size
    # Allow large images at modest Wi-Fi rates, while retaining a hard bound.
    receiver_seconds=min(1800,max(180,(count+524287)//524288+60))
    # Data only: no command parser; bounded bytes, duration and source address.
    script=f'''#!/bin/sh
set -eu
umask 077
usr=/tmp/a6-native/tools/usr
nft() {{ "$usr/lib/ld-linux-armhf.so.3" --library-path "$usr/lib" "$usr/bin/nft" "$@"; }}
handle=
cleanup() {{ test -z "$handle" || nft delete rule ip a6_guard input handle "$handle"; }}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
nft 'insert rule ip a6_guard input iifname "wlan0" ip saddr {host} tcp dport 8085 accept comment "{stem[5:]}"'
handle=$(nft -a list chain ip a6_guard input | busybox awk '/{stem[5:]}/ {{print $NF}}')
case "$handle" in ''|*[!0-9]*) exit 1;; esac
busybox timeout {receiver_seconds} busybox nc -l -p 8085 {address} | busybox head -c {count-offset} {'>>' if offset else '>'}{destination}.part
test "$(busybox stat -c %s {destination}.part)" = {count}
printf '%s  %s\\n' {expected} {destination}.part | busybox sha256sum -c -
busybox mv {destination}.part {destination}
'''
    phone.upload(script.encode(),stem+'.sh')
    phone.checked("busybox setsid busybox sh -c 'echo $$ >"+stem+".pid; busybox sh "+stem+'.sh; echo $? >'+stem+".rc' </dev/null >"+stem+'.private.log 2>&1 &')
    for _ in range(40):
        try:target=socket.create_connection((address,8085),timeout=2);break
        except (ConnectionRefusedError,TimeoutError):time.sleep(.25)
    else:raise RuntimeError('Wi-Fi data receiver unavailable')
    try:
        with target,source.open('rb') as stream:
            stream.seek(offset);target.settimeout(20)
            while chunk:=stream.read(65536):target.sendall(chunk);time.sleep(.01)
            target.shutdown(socket.SHUT_WR)
    except OSError:
        phone.checked('read pid < '+stem+'.pid; case "$pid" in \'\'|*[!0-9]*) exit 1;; esac; test "$pid" -gt 1 && kill -TERM -"$pid"; busybox sleep 1')
        raise RuntimeError('Wi-Fi image transfer stalled; owned receiver stopped, prefix retained') from None
    # Wait for hash verification and EXIT firewall cleanup, not just socket EOF.
    for _ in range(45):
        output=phone.checked('if test -f '+stem+'.rc; then cat '+stem+'.rc; fi')
        values=[v for v in output.replace('\r','').splitlines() if v in ('0','1','2','124')]
        if values:
            if values[-1]!='0':raise RuntimeError('Phone image verification failed; private log retained')
            phone.checked('! ('+'"/tmp/a6-native/tools/usr/lib/ld-linux-armhf.so.3" --library-path /tmp/a6-native/tools/usr/lib /tmp/a6-native/tools/usr/bin/nft list chain ip a6_guard input | busybox grep -q '+stem[5:]+')')
            return
        time.sleep(1)
    raise RuntimeError('Phone image verification timed out; private log retained')

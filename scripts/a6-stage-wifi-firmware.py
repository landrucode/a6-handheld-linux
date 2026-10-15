#!/usr/bin/env python3
"""Stage the pinned private TRX into RAM over the existing USB ECM transport."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import socket
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    package=json.loads((ROOT/'build/wifi-firmware/a6-download-package.json').read_text())
    path=(ROOT/package['output']).resolve()
    if not path.is_relative_to(ROOT/'build/wifi-firmware'):
        raise ValueError('package outside private build/')
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=package['sha256'] or len(data)!=456108:
        raise ValueError('package hash/size mismatch')
    spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    nonce=secrets.token_hex(8);evidence=[]
    log=ROOT/'build/session-logs'/('wifi-firmware-stage-'+nonce+'.console.txt')
    def serial(command,timeout=20):
        r=m.serial(command,timeout=timeout);evidence.append(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('ACM staging command failed')
        return r.stdout
    destination='/lib/firmware/a6-centennial-tdk.trx'
    temporary='/tmp/a6-wifi-fw-'+nonce+'.part';status='/tmp/a6-wifi-fw-'+nonce+'.status'
    try:
        pre=serial('echo 1 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; cat '+m.BASE+'/status; cat '+m.BASE+'/download; '
                   'if test -e '+destination+'; then busybox sha256sum '+destination+'; else echo A6_FW_DESTINATION_EMPTY; fi')
        if re.search(r'(?m)^'+digest+r'  '+re.escape(destination)+r'\r?$',pre):
            print('Verified firmware already present in RAM; reusable for more attempts')
            return
        if (not re.search(r'(?m)^A6_WIFI_EHCI_ENUM_V2 attempted=[01] ',pre) or
            not re.search(r'(?m)^A6_WIFI_USB_DOWNLOAD_V1 enabled=1 ',pre) or
            not re.search(r'(?m)^A6_FW_DESTINATION_EMPTY\r?$',pre)):
            raise RuntimeError('download image/RAM destination refused')
        worker='umask 077; busybox timeout 20 busybox nc -l -p 8083 192.168.7.2 > '+temporary+'; echo $? > '+status
        serial("busybox setsid busybox sh -c '"+worker+"' </dev/null >/tmp/a6-wifi-fw-listener.log 2>&1 & echo A6_FW_LISTENING")
        deadline=time.monotonic()+5
        while True:
            try:
                target=socket.create_connection(('192.168.7.2',8083),timeout=1)
                break
            except ConnectionRefusedError:
                if time.monotonic()>=deadline:raise
                time.sleep(0.1)
        with target:
            target.settimeout(15);target.sendall(data);target.shutdown(socket.SHUT_WR)
        command=('echo 2 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; sleep 1; test -f '+status+' && test "$(cat '+status+')" = 0 && '
                 "printf '%s  %s\\n' '"+digest+"' "+temporary+' | busybox sha256sum -c - && '
                 'busybox mkdir -p /lib/firmware && busybox chmod 0700 /lib/firmware && '
                 'busybox chmod 0400 '+temporary+' && busybox mv '+temporary+' '+destination+' && '
                 'echo A6_FW_RAM_SHA256_VERIFIED')
        output=serial(command)
        if not re.search(r'(?m)^A6_FW_RAM_SHA256_VERIFIED\r?$',output):
            raise RuntimeError('RAM firmware validation failed')
        print('RAM firmware staged and SHA256 verified:',len(data),'bytes')
    finally:
        log.write_text('\n'.join(evidence))
        print('Private evidence:',log.relative_to(ROOT))


if __name__=='__main__':main()

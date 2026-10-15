#!/usr/bin/env python3
"""Execute staging orchestration with mocked ACM/socket and private package fixtures."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stage',ROOT/'scripts/a6-stage-wifi-firmware.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);(root/'build/wifi-firmware').mkdir(parents=True);(root/'build/session-logs').mkdir()
    data=b'x'*456108;package=root/'build/wifi-firmware/test.trx';package.write_bytes(data)
    manifest={'output':'build/wifi-firmware/test.trx','sha256':hashlib.sha256(data).hexdigest()}
    (root/'build/wifi-firmware/a6-download-package.json').write_text(json.dumps(manifest))
    m.ROOT=root
    commands=[];sent=[];fault=0
    def serial(command,timeout=20):
        commands.append(command)
        assert '/run' not in command and 'bootx' not in command
        if len(commands)==1:
            out='A6_WIFI_EHCI_ENUM_V2 attempted='+('1' if fault==1 else '0')+' result=0\nA6_WIFI_USB_DOWNLOAD_V1 enabled=1 result=-11\nA6_FW_DESTINATION_EMPTY\n'
        elif len(commands)==2:
            assert 'umask 077; busybox timeout 20 busybox nc -l -p 8083' in command
            out='A6_FW_LISTENING\n'
        else:
            assert manifest['sha256'] in command and 'busybox sha256sum -c -' in command and 'chmod 0400' in command
            out='' if fault==2 else 'A6_FW_RAM_SHA256_VERIFIED\n'
        return SimpleNamespace(returncode=0,stdout=out,stderr='')
    fake=SimpleNamespace(BASE='/sys/firmware/a6_wifi_ehci_enum',serial=serial)
    loader=SimpleNamespace(exec_module=lambda module:None)
    target=SimpleNamespace(sendall=lambda b:sent.append(b),shutdown=lambda x:None,settimeout=lambda x:None)
    class Socket:
        def __enter__(self):return target
        def __exit__(self,*args):return False
        def settimeout(self,n):target.settimeout(n)
        def sendall(self,b):target.sendall(b)
        def shutdown(self,n):target.shutdown(n)
    def connect(address,timeout):
        assert address==('192.168.7.2',8083) and timeout==1
        if fault==3:raise socket.timeout('fixture timeout')
        return Socket()
    for fault in range(4):
        commands.clear();sent.clear()
        with patch.object(m.importlib.util,'spec_from_file_location',return_value=SimpleNamespace(loader=loader)),patch.object(m.importlib.util,'module_from_spec',return_value=fake),patch.object(m.socket,'create_connection',side_effect=connect),contextlib.redirect_stdout(io.StringIO()):
            try:m.main()
            except (RuntimeError,socket.timeout):assert fault
            else:assert fault==0
        if fault==0:assert sent==[data] and len(commands)==3
        if fault==1:assert not sent and len(commands)==1
        if fault==3:assert not sent and len(commands)==2
print('RAM staging: exact payload/hash, bounded listener, fresh-image refusal, SHA refusal and socket failure paths passed')

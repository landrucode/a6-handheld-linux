#!/usr/bin/env python3
"""Execute the compact collector shell command with fake read-only endpoints."""
import importlib.util
import itertools
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('capture',ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
marker='A6_ENUM_END_'+'0'*16
for identity,otp,download,execute,runtime,rx,loopback in itertools.product((False,True),repeat=7):
    command=m.build_capture_command('/tmp/a6-ehci-'+'0'*16,identity,otp,download,execute,runtime,rx,loopback)
    split=len(marker)//2
    suffix="; printf '%s%s\\n' "+shlex.quote(marker[:split])+' '+shlex.quote(marker[split:])
    assert len((command+suffix+'\n').encode()) < 1024
    subprocess.run(['sh','-n','-c',command+suffix],check=True)
with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    for name in ('run','status','identity','otp','download','execute','runtime','bulk_rx','loopback','progress'):
        (root/name).write_text(name+'\n')
    command=m.build_capture_command('/tmp/a6-ehci-'+'1'*16,True,True,True,True,True,True,True)
    command=command.replace('b='+m.BASE,'b='+shlex.quote(str(root)))
    command=command.replace('s=/tmp/a6-ehci-'+'1'*16,'s='+shlex.quote(str(root/'evidence')))
    # Preserve actual background/poll/completion flow, mute hardware-only tails.
    command=command[:command.index('cat /proc/interrupts')].rstrip().rstrip(';')
    r=subprocess.run(['sh','-c',command+suffix],capture_output=True,text=True,timeout=5,check=True)
    assert (root/'run').read_text()=='enumerate-once-n42-wlan\n'
    assert (root/'evidence.done').read_text()=='done\n'
    assert 'probe_write_rc=0' in r.stdout and marker in r.stdout
    for name in ('status','identity','otp','download','execute','runtime','bulk_rx','loopback'):assert name+'\n' in r.stdout
print('Collector: all mode lines including completion printf fit1024; actual background/poll/final capture shell flow passed')

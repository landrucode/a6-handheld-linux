#!/usr/bin/env python3
"""Bounds, placeholder refusal and fixed-clock compatibility of audio capture."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def prop(k,v):return k.encode().ljust(32,b'\0')+struct.pack('<I',len(v))+v+b'\0'*((-len(v))%4)
def node(props,children=()):return struct.pack('<II',len(props),len(children))+b''.join(prop(k,v) for k,v in props)+b''.join(children)
def speaker(extra=()):return node([('name',b'audio-speaker\0'),('compatible',b'audio-control,cs35l19\0'),*extra])
with tempfile.TemporaryDirectory() as td:
 so=Path(td)/'capture.so';subprocess.run(['cc','-shared','-fPIC','-O2','-DA6_CAPTURE_TEST=1','-std=c11','-Wall','-Wextra','-Werror','-DA6_CAPTURE_CLOCK=1','-DA6_CAPTURE_CPU_CLOCK=1','-DA6_CAPTURE_AUDIO=1',str(ROOT/'boot/arm/capture-memory.c'),'-o',str(so)],check=True)
 f=ctypes.CDLL(str(so)).a6_parse_memory;f.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint)]
 def run(data):
  a=(ctypes.c_uint*706)();a[0]=a[705]=0xaabbccdd;p=ctypes.cast(ctypes.byref(a,4),ctypes.POINTER(ctypes.c_uint));s=f(data,len(data),p);assert a[0]==a[705]==0xaabbccdd;return s,list(a)[1:-1]
 config=bytes(range(20));rdc=b'\x01\x02\x03\x04';cal=b'c'*256
 data=node([('name',b'device-tree\0')],[speaker([('speaker-config',config),('speaker-rdc',rdc),('speaker-calib',cal)])])
 status,w=run(data);assert status==1 and w[512:518]==[0x53504431,7,1,20,4,256];assert struct.pack('<704I',*w)[0x820:0x834]==config
 for n in range(len(data)):assert run(data[:n])[0]!=1
 for value in (b'syscfg/SRdc/0x4,zeroes/0x4\0',b'x'*5):
  _,w=run(node([('name',b'device-tree\0')],[speaker([('speaker-rdc',value)])]));assert not w[513]&2
 _,w=run(node([('name',b'device-tree\0')],[speaker(),speaker()]));assert w[513]&32
 for n in (0,257,4096):
  _,w=run(node([('name',b'device-tree\0')],[speaker([('speaker-calib',b'x'*n)])]));assert w[513]&16
 _,w=run((ROOT/'build/touch-research/DeviceTree-ios10.raw').read_bytes());assert w[512]==0x53504431 and w[513]&1 and not w[513]&2
print('PASS: populated audio bytes, unresolved syscfg refusal, truncation, duplicates and capture bounds')

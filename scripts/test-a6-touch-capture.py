#!/usr/bin/env python3
"""Host-only adversarial tests for the read-only calibration capture extension."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
repo=Path(__file__).resolve().parents[1]
def prop(name,data):
    return name.encode().ljust(32,b'\0')+struct.pack('<I',len(data))+data+b'\0'*(-len(data)%4)
def node(props,children=()):
    return struct.pack('<II',len(props),len(children))+b''.join(prop(*p) for p in props)+b''.join(children)
cal=bytes(range(256))*4
prox=bytes(range(128))
def touch(extra=(),compatible=b'multi-touch,n41\0',calibration=cal):
    return node([('multi-touch-calibration',calibration),('prox-calibration',prox),
        ('compatible',compatible),('name',b'multi-touch\0'),*extra])
with tempfile.TemporaryDirectory() as d:
    so=Path(d)/'capture.so'
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DA6_CAPTURE_TEST',
        '-DA6_CAPTURE_TOUCH','-shared','-fPIC',str(repo/'boot/arm/capture-memory.c'),'-o',str(so)],check=True)
    fn=ctypes.CDLL(str(so)).a6_parse_memory
    fn.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint)]
    def run(data):
        storage=(ctypes.c_uint*706)();storage[0]=storage[-1]=0xdeadbeef
        ptr=ctypes.cast(ctypes.byref(storage,4),ctypes.POINTER(ctypes.c_uint))
        status=fn(ctypes.create_string_buffer(data),len(data),ptr)
        assert storage[0]==storage[-1]==0xdeadbeef
        words=list(storage)[1:-1]
        return status,words,struct.pack('<704I',*words)
    data=node([('name',b'device-tree\0')],[touch()])
    status,w,b=run(data)
    assert status==1 and w[25:32]==[3,3,1,1024,128,1020,127]
    assert b[0x600:0xa00]==cal and b[0xa00:0xa80]==prox
    assert b[0xa80:]==bytes(128)
    for end in range(len(data)):
        assert run(data[:end])[0]!=1
    assert run(data+b'\0')[0]!=1
    for length in (0,1,1023,1025,4096):
        _,w,_=run(touch(calibration=b'x'*length));assert w[26]&4 and w[28]==0
    _,w,_=run(touch(extra=[('multi-touch-calibration',cal)]));assert w[26]&4
    _,w,_=run(node([('name',b'root\0')],[touch(),touch()]));assert w[26]&8 and w[27]==2
    for wrong in (b'',b'multi-touch,n4\0',b'multi-touch,n42\0',b'multi-touch,n41x'):
        _,w,_=run(touch(compatible=wrong));assert w[27]==0 and w[26]==0
    many=node([('name',b'memory-map\0')]+[(f'r{i}',b'x'*8) for i in range(40)])
    _,w,b=run(node([('name',b'root\0')],[many,touch()]))
    assert w[5]==19 and w[7]&1 and b[0x600:0xa00]==cal
    status,w,b=run((repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw').read_bytes())
    assert status==1 and w[5]==19 and w[7]==0 and w[25:32]==[3,3,1,1024,128,0,0]
    print('PASS calibration bytes, zero template, wrong match/length, duplicates, all truncations, record cap and output sentinels')

#!/usr/bin/env python3
"""Adversarial host checks for fixed-size live clock-table capture."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import sys
cpu_mode = '--cpu' in sys.argv[1:]
revision = 5 if cpu_mode else 4
repo=Path(__file__).resolve().parents[1]
def prop(name,data):
    return name.encode().ljust(32,b'\0')+struct.pack('<I',len(data))+data+b'\0'*(-len(data)%4)
def node(props,children=()):
    return struct.pack('<II',len(props),len(children))+b''.join(prop(*p) for p in props)+b''.join(children)
table=bytes(range(128))*3
def armio(value=table,extra=(),name=b'arm-io\0'):
    return node([('clock-frequencies',value),('name',name),*extra])
def root(children):return node([('name',b'device-tree\0')],children)
with tempfile.TemporaryDirectory() as d:
    so=Path(d)/'capture.so'
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DA6_CAPTURE_TEST',
        '-DA6_CAPTURE_CLOCK',*(['-DA6_CAPTURE_CPU_CLOCK'] if cpu_mode else []),
        '-shared','-fPIC',str(repo/'boot/arm/capture-memory.c'),'-o',str(so)],check=True)
    fn=ctypes.CDLL(str(so)).a6_parse_memory
    fn.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint)]
    def run(data):
        storage=(ctypes.c_uint*706)();storage[0]=storage[-1]=0xdeadbeef
        ptr=ctypes.cast(ctypes.byref(storage,4),ctypes.POINTER(ctypes.c_uint))
        status=fn(ctypes.create_string_buffer(data),len(data),ptr)
        assert storage[0]==storage[-1]==0xdeadbeef
        words=list(storage)[1:-1]
        return status,words,struct.pack('<704I',*words)
    data=root([armio()]);status,w,b=run(data)
    assert status==1 and w[25:30]==[revision,1,1,384,381]
    assert b[0x600:0x780]==table and b[0x780:]==bytes(0x380)
    for end in range(len(data)):assert run(data[:end])[0]!=1
    assert run(data+b'\0')[0]!=1
    for length in (0,1,383,385,4096):
        _,w,_=run(root([armio(b'x'*length)]));assert w[26]&4 and w[28]==0
    _,w,_=run(root([armio(extra=[('clock-frequencies',table)])]));assert w[26]&4
    _,w,_=run(root([armio(),armio()]));assert w[26]&8 and w[27]==2
    for name in (b'',b'arm-io',b'arm-iox\0',b'arm-i\0'):
        _,w,_=run(root([armio(name=name)]));assert w[27]==0
    _,w,_=run(root([root([armio()])]));assert w[27]==0
    many=node([('name',b'memory-map\0')]+[(f'r{i}',b'x'*8) for i in range(40)])
    _,w,b=run(root([many,armio()]));assert w[5]==19 and w[7]&1 and b[0x600:0x780]==table
    status,w,b=run((repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw').read_bytes())
    assert status==1 and w[25:30]==[revision,1,1,384,0] and w[7]==0
    if cpu_mode:
        def cpu(value=struct.pack('<I',24000000),extra=(),name=b'cpu0\0',state=b'running\0'):
            return node([('name',name),('fixed-frequency',value),('state',state),*extra])
        def cpus(children,extra=()):return node([('name',b'cpus\0'),*extra],children)
        def run_cpu(children):
            status,w,b=run(root([armio(),*children]));return status,w[480:486],b
        for size in (4,8):
            data=root([armio(),cpus([cpu((24000000).to_bytes(size,'little'))])])
            status,w,b=run(data)
            assert status==1 and w[480:486]==[3,1,size,24000000,0,1]
            assert b[0x798:]==bytes(0xb00-0x798)
            for end in range(len(data)):assert run(data[:end])[0]!=1
        for size in (0,1,3,5,7,9,1024):
            _,c,_=run_cpu([cpus([cpu(b'x'*size)])]);assert c[0]&4
        _,c,_=run_cpu([cpus([cpu(extra=[('fixed-frequency',b'xxxx')])])]);assert c[0]&4
        _,c,_=run_cpu([cpus([cpu(),cpu()])]);assert c[0]&8 and c[1]==2
        _,c,_=run_cpu([cpus([cpu()]),cpus([cpu()])]);assert c[5]==2
        for extra in ([('state',b'running\0')],[('name',b'cpu1\0')]):
            _,c,_=run_cpu([cpus([cpu(extra=extra)])]);assert c[0]&16
        _,c,_=run_cpu([cpus([cpu()],extra=[('name',b'other\0')])]);assert c[0]&16
        for children in ([cpu()],[root([cpu()])],[cpus([node([('name',b'nested\0')],[cpu()])])],
                         [cpus([]),node([('name',b'other\0')],[cpu()])]):
            _,c,_=run_cpu(children);assert c[1]==0
        for name in (b'cpu0',b'cpu0x\0',b'cpu1\0'):
            _,c,_=run_cpu([cpus([cpu(name=name)])]);assert c[1]==0
        _,c,_=run_cpu([cpus([cpu(state=b'waiting\0')])]);assert not c[0]&2
        _,c,_=run_cpu([cpus([cpu((1<<40).to_bytes(8,'little'))])]);assert c[4]==256
        _,w,_=run((repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw').read_bytes())
        assert w[480:486]==[3,1,4,0,0,1]
        print('PASS CPU fixed-clock capture: exact path/state, 32/64-bit, truncation, ambiguity and duplicates')
    print('PASS clock-table capture: exact bytes, static zeros, truncation, bad lengths/names/depth, duplicates, record cap and sentinels')

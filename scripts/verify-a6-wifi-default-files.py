#!/usr/bin/env python3
"""Verify stock loader's default FilesDB dictionary lookup offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    kernel=(ROOT/'build/touch-research/Kernelcache-ios10.raw').read_bytes()
    digest=hashlib.sha256(kernel).hexdigest()
    assert digest=='bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
    spec=importlib.util.spec_from_file_location('extract',ROOT/'scripts/extract-a6-stock-touch.py')
    e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
    path=ROOT/'build/touch-research/ios10-wifi-kexts/com.apple.driver.AppleBCMWLANCoreLegacy-analysis.macho'
    blob=path.read_bytes()
    def read(data,address,length):
        segs=[struct.unpack_from('<IIII',c,24) for k,c in e.commands(data) if k==1]
        offsets=[o+address-v for v,_,o,n in segs if v<=address and address+length<=v+n]
        assert len(offsets)==1
        return data[offsets[0]:offsets[0]+length]
    def word(address):
        return struct.unpack('<I',read(kernel,address,4))[0]
    instructions={}
    for start,end in ((0x80b90b9c,0x80b90baa),(0x80b86730,0x80b8676c)):
        assert read(blob,start,end-start)==read(kernel,start,end-start)
        output=subprocess.check_output(['llvm-objdump','-d','--triple=thumbv7-apple-ios',
            f'--start-address={start:#x}',f'--stop-address={end:#x}',str(path)],text=True)
        for line in output.splitlines():
            m=re.match(r'^([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+(.+)$',line)
            if m:instructions[int(m[1],16)]=re.sub(r'\s+',' ',m[2]).split(' @ ',1)[0].strip()
    expected={0x80b90b9e:'add r0, pc',0x80b90ba0:'bl 0x80bd6bf0',
              0x80b90ba6:'add r1, pc',0x80b90ba8:'str r0, [r1]',
              0x80b86746:'ldr.w r2, [r0, #0x90]',0x80b8674c:'add r0, pc',
              0x80b8674e:'ldr r1, [r0]',0x80b86750:'mov r0, r6',
              0x80b86752:'blx r2',0x80b8675a:'ldr.w r8, [r1]',
              0x80b86760:'bl 0x80bd6800',0x80b86768:'beq.w 0x80b86944 <__text+0x2dda4>'}
    for address,text in expected.items():assert instructions.get(address)==text,(hex(address),instructions.get(address))
    string=(word(0x80b90c24)+0x80b90b9e+4)&0xffffffff
    assert read(kernel,string,8)==b'default\0'
    symbol=(word(0x80b90c28)+0x80b90ba6+4)&0xffffffff
    assert (word(0x80b86aa0)+0x80b8674c+4)&0xffffffff==symbol
    meta_slot=(word(0x80b86aa4)+0x80b86756+4)&0xffffffff
    assert word(meta_slot)==0x803d8c40 and word(word(meta_slot))==0x80456244
    assert word(0x803d8c48+8+0x90)&~1==0x802fa2a4
    print(json.dumps({'kernel_sha256':digest,'default_symbol_lookup_verified':True,
        'dictionary_cast_verified':True,'lookup':'OSDictionary::getObject(OSSymbol default)',
        'default_read_before_optional_overrides':True,
        'limitation':'No claim about untested runtime overrides or firmware execution.'},indent=2))


if __name__=='__main__':main()

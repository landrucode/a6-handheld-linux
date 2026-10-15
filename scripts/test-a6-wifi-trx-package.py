#!/usr/bin/env python3
"""Check normalization/token/CRC round-trip and malformed packing input refusal."""
import importlib.util
from pathlib import Path
import secrets
import struct
import zlib

ROOT=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load(ROOT/'scripts/prepare-a6-wifi-trx.py','pack')
h=load(ROOT/'.deps/cascadia-wifi-reference/scripts/trx-add-nvram.py','helper')
body=b'firmware-fixture'
fw=bytearray(struct.pack('<7I',0x30524448,28+len(body)+12,0,0x10020,len(body),0x81,0)+body+bytes(12))
struct.pack_into('<I',fw,8,h.trx_crc(fw))
address=bytearray(secrets.token_bytes(6));address[0]=(address[0]|2)&254
mac=':'.join(f'{x:02x}' for x in address)
image,n=m.pack(bytes(fw),'# test fixture\n a = 1 \n b=2 # comment\n',mac,h)
magic,length,crc,flags,download,second,third=struct.unpack_from('<7I',image)
assert length==len(image) and third==n and download==len(body) and second==0x81
assert (~zlib.crc32(image[12:])&0xffffffff)==crc
nv=image[28+len(body):];assert nv[:-4].startswith(b'a=1\0b=2\0macaddr='+mac.encode()+b'\0\0')
words=(len(nv)-4)//4;assert struct.unpack_from('<I',nv,len(nv)-4)[0]==((~words&65535)<<16|words)
invalid=[]
for position in (0,4,8,12,16,24,len(fw)-1):
    bad=bytearray(fw);bad[position]^=1;invalid.append(bytes(bad))
invalid.append(bytes(fw[:20]))
for data in invalid:
    try:m.pack(data,'a=1',mac,h)
    except ValueError:pass
    else:raise AssertionError('malformed TRX accepted')
for nvram,badmac in [('macaddr='+mac,mac),('a=1','bad'),('a=1',':'.join(['00']*6)),('a=1',':'.join(['ff']*6))]:
    try:m.pack(bytes(fw),nvram,badmac,h)
    except ValueError:pass
    else:raise AssertionError('conflicting/invalid MAC accepted')
print('Cascadia packing: payload preservation, NVRAM normalization/token, independent CRC and malformed input refusals passed')

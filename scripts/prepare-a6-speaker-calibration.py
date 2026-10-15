#!/usr/bin/env python3
"""Extract populated speaker properties from the owner's private boot capture.

No NAND/syscfg writes or device access. Factory bytes stay in ignored build/.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
ROOT = Path(__file__).resolve().parents[1]
def decode(data):
    if len(data)!=2816:raise ValueError('expected bounded boot capture')
    w=struct.unpack('<704I',data)
    if w[0]!=0x41364d31 or w[1]!=1 or w[7] or w[512]!=0x53504431 or w[514]!=1 or w[513]&0x30:
        raise ValueError('malformed or ambiguous live capture')
    result={}
    for bit,index,offset,name in [(1,515,0x820,'speaker-config'),(2,516,0x840,'SRdc'),(4,517,0x850,'speaker-calib')]:
        if not w[513]&bit:continue
        length=w[index]
        if (bit==1 and length!=20) or (bit==2 and length!=4) or (bit==4 and length!=20):raise ValueError('invalid '+name+' size')
        payload=data[offset:offset+length]
        result[name]=payload
    return w[513],result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    destination=a.output.resolve()
    if not destination.is_relative_to(ROOT/'build'):raise ValueError('factory output must stay in ignored build/')
    os.umask(0o077);flags,properties=decode(a.capture.read_bytes());destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    report={'flags':flags,'source_sha256':hashlib.sha256(a.capture.read_bytes()).hexdigest(),'properties':[]}
    for name,payload in properties.items():
        target=destination/(name+'.private.bin');target.write_bytes(payload);target.chmod(0o600)
        report['properties'].append({'name':name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(), 'stock_version_usable': name!='speaker-calib' or struct.unpack_from('<I',payload,16)[0]==1})
    target=destination/'manifest.private.json';target.write_text(json.dumps(report,indent=2)+'\n');target.chmod(0o600)
    print('Extracted private speaker properties:', ', '.join(properties) or 'none')
if __name__=='__main__':main()

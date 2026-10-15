#!/usr/bin/env python3
"""Analyze ignored RX bytes without exporting raw content, addresses or strings."""
from pathlib import Path
import argparse, hashlib, json, re
ROOT=Path(__file__).resolve().parents[1]
def analyze(data):
 def header(off):
  p=data[off:off+16]
  flags=int.from_bytes(p[:2],'little');length=int.from_bytes(p[4:6],'little')
  total=sum(int.from_bytes(p[i:i+2],'little') for i in range(0,16,2))
  total=(total&65535)+(total>>16);total=(total&65535)+(total>>16)
  return dict(offset=off,flags=f'{flags:04x}',kind=(flags>>12)&7,present=bool(flags&32768),length=length,checksum_valid=total==65535,bounded=16<=length<=len(data)-off)
 valid=[header(i) for i in range(max(0,len(data)-15))]
 valid=[h for h in valid if h['present'] and h['checksum_valid'] and h['bounded']]
 # Exact chain and explicitly bounded zero-padding hypothesis, never skip nonzero bytes.
 walks=[]
 for alignment in (1,4,16):
  off=0;records=[]
  while off+16<=len(data):
   h=header(off)
   if not(h['present'] and h['checksum_valid'] and h['bounded']):break
   records.append(h);end=off+h['length'];nxt=((end+alignment-1)//alignment)*alignment
   if any(data[end:nxt]):break
   off=nxt
  walks.append(dict(alignment=alignment,records=records,stop_offset=off,complete=bool(records) and off==len(data)))
 events=[]
 for off in range(max(0,len(data)-71)):
  p=data[off:];version=int.from_bytes(p[24:26],'big');body=int.from_bytes(p[44:48],'big')
  if p[12:16]==bytes.fromhex('886c8001') and p[19:24]==bytes.fromhex('0010180001') and version in (1,2) and body<=len(p)-72:
   events.append(dict(ethernet_offset=off,event=int.from_bytes(p[28:32],'big'),version=version,body_bytes=body))
 blocks=[data[i:i+16] for i in range(0,len(data),16)]
 return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),first_header=header(0) if len(data)>=16 else None,valid_headers=valid,chain_walks=walks,canonical_events=events,nonzero_aligned_blocks=[i*16 for i,b in enumerate(blocks) if any(b)],repeated_nonzero_blocks=[i*16 for i,b in enumerate(blocks) if any(b) and len(b)==16 and blocks.count(b)>1],printable_bytes=sum(32<=v<=126 for v in data),printable_fraction=sum(32<=v<=126 for v in data)/len(data) if data else 0,printable_runs=[dict(offset=m.start(),bytes=len(m[0])) for m in re.finditer(rb'[\x20-\x7e]{4,}',data)])
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 for path in (a.packet,a.output):
  if not path.resolve().is_relative_to(ROOT/'build'):p.error('Inputs and reports must remain private under build/')
 report=analyze(a.packet.read_bytes())
 with a.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 a.output.chmod(0o400)
 print('Saved outer framing analysis; valid headers:',len(report['valid_headers']),'canonical events:',len(report['canonical_events']))
if __name__=='__main__':main()

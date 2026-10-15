#!/usr/bin/env python3
"""Offline scan journal analysis; counts/channels/RSSI only on stdout."""
from pathlib import Path
import json,struct,sys
ROOT=Path(__file__).resolve().parents[1]
def analyze(path):
 path=path.resolve()
 if not path.is_relative_to(ROOT/'build'):raise ValueError('private journals stay under build/')
 data=path.read_bytes();cursor=0;bsses={};partial=0;complete=0;events={};countries=[];mpc=[];masks=[];bodies=[]
 while cursor<len(data):
  if len(data)-cursor<8:raise ValueError('short journal header')
  tag,n,ms=struct.unpack_from('<HHI',data,cursor);cursor+=8
  if n>len(data)-cursor:raise ValueError('short journal body')
  p=data[cursor:cursor+n];cursor+=n
  if tag<0x8000:
   if n<16:continue
   cmd,length,flags,status=struct.unpack_from('<IIII',p)
   if status or flags&1:continue
   q=p[16:16+length]
   if tag in (20,25,39) and len(q)>=12:countries.append({'id':tag,'abbrev':q[:4].split(b'\0')[0].decode('ascii'),'code':q[8:12].split(b'\0')[0].decode('ascii'),'revision':struct.unpack_from('<i',q,4)[0]})
   if tag in (23,35) and len(q)>=4:mpc.append({'id':tag,'value':int.from_bytes(q[:4],'little')})
   if tag in (21,28,37) and len(q)>=9:masks.append({'id':tag,'scan_complete':bool(q[3]&4),'escan':bool(q[8]&32),'TRACE':bool(q[6]&16)})
   continue
  if n<4:continue
  if int.from_bytes(p[:2],'little')&0x8000:
   if n<16 or int.from_bytes(p[4:6],'little')!=n:continue
   words=struct.unpack_from('<8H',p);s=sum(words);s=(s&65535)+(s>>16);s=(s&65535)+(s>>16)
   if s!=65535:continue
   p=p[16:]
  if len(p)<4 or p[0]>>4!=2 or p[2]&15:continue
  off=4+p[3]*4
  if len(p)<off+72 or p[off+12:off+16]!=b'\x88\x6c\x80\x01' or p[off+19:off+24]!=b'\x00\x10\x18\x00\x01':continue
  event=int.from_bytes(p[off+28:off+32],'big');status=int.from_bytes(p[off+32:off+36],'big');nbody=int.from_bytes(p[off+44:off+48],'big')
  if nbody>len(p)-off-72:continue
  events[event]=events.get(event,0)+1
  if event!=69:continue
  q=p[off+72:off+72+nbody]
  if len(q)<12:continue
  total,version,sync,count=struct.unpack_from('<IIHH',q)
  if total>len(q) or version!=109 or sync!=0x1234:continue
  if status==0 and count==0 and total==12:complete+=1;continue
  if status!=8 or count!=1 or total<140:continue
  b=q[12:total];bv,length=struct.unpack_from('<II',b)
  if bv!=109 or length!=len(b) or b[18]>32:continue
  ie=int.from_bytes(b[116:118],'little');size=int.from_bytes(b[120:124],'little')
  if ie<128 or ie>len(b) or size>len(b)-ie:continue
  pos=ie;end=ie+size
  while pos<end:
   if end-pos<2 or b[pos+1]>end-pos-2:break
   pos+=b[pos+1]+2
  if pos!=end:continue
  partial+=1;bodies.append(q[:total]);key=b[8:14]
  bsses[key]={'channel':b[88],'rssi_dbm':int.from_bytes(b[78:80],'little',signed=True)}
 return {'partial_events':partial,'completion_events':complete,'unique_BSS':len(bsses),'BSS_metadata':list(bsses.values()),'event_counts':events,'country_readbacks':countries,'mpc_readbacks':mpc,'event_masks':masks},bodies
if __name__=='__main__':
 report,_=analyze(Path(sys.argv[1]));print(json.dumps(report,indent=2))

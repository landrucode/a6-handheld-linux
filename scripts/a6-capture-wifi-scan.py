#!/usr/bin/env python3
"""Retained scan snapshot only; no firmware or radio commands."""
from pathlib import Path
import base64,json,re,secrets,subprocess,sys,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
BASE='/sys/firmware/a6_wifi_ehci_enum'
def parse(console,marker):
 lines=console.replace('\r','').splitlines();begin,end=marker+'_BEGIN',marker+'_END'
 if lines.count(begin)!=1 or lines.count(end)!=1:raise ValueError('ambiguous markers')
 first,last=lines.index(begin),lines.index(end)
 if first>=last:raise ValueError('reversed markers')
 statuses=[l for l in lines[:first] if l.startswith('A6_WIFI_USB_SCAN_V1 ')]
 if len(statuses)!=1:raise ValueError('ambiguous status')
 f=dict(re.findall(r'(\w+)=([^ ]+)',statuses[0]))
 for k,v in [('enabled','1'),('passive','1'),('association','0'),('bulk_out','0')]:
  if f.get(k)!=v:raise ValueError('scan contract mismatch')
 if int(f.get('attempted','0'))<1:raise ValueError('scan not attempted')
 if not 0<=int(f['tx'])<=23 or not 0<=int(f['rx'])<=23 or not 0<=int(f['receives'])<=64:raise ValueError('unbounded transactions')
 data=base64.b64decode(''.join(lines[first+1:last]),validate=True)
 if len(data)>136000 or len(data)!=int(f['bytes']):raise ValueError('snapshot bound/status mismatch')
 cursor=0;records=[];ids=[];bulk=[];previous_time=0
 while cursor<len(data):
  if len(data)-cursor<8:raise ValueError('short journal header')
  tag=int.from_bytes(data[cursor:cursor+2],'little');n=int.from_bytes(data[cursor+2:cursor+4],'little');ms=int.from_bytes(data[cursor+4:cursor+8],'little');cursor+=8
  if n>len(data)-cursor or ms<previous_time:raise ValueError('invalid length/time')
  if 20<=tag<=39:
   if n>276:raise ValueError('invalid control record')
   ids.append(tag)
  elif 0x8000<=tag<0x8040:
   if n>2048 or (bulk and tag<=bulk[-1]):raise ValueError('invalid bulk record')
   bulk.append(tag)
  else:raise ValueError('unexpected tag')
  records.append({'tag':tag,'bytes':n,'arrival_ms':ms,'sha256':hashlib.sha256(data[cursor:cursor+n]).hexdigest()});cursor+=n;previous_time=ms
 if len(ids)>int(f['rx']) or len(bulk)>int(f['receives']):raise ValueError('record count mismatch')
 return data,{'status':f,'records':records,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def private_write(p,data):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data)
 p.chmod(0o400)
def main():
 marker='A6_SCAN_'+secrets.token_hex(8);emit=lambda v:"printf '%s%s\\n' "+v[:len(v)//2]+' '+v[len(v)//2:]
 cmd=f'cat {BASE}/preflight; '+emit(marker+'_BEGIN')+f'; busybox base64 {BASE}/preflight_data; '+emit(marker+'_END')
 res=subprocess.run([sys.executable,str(ROOT/'scripts/a6-usb-acm-direct.py'),cmd,'--until',marker+'_END','--timeout','20'],capture_output=True,timeout=30)
 prefix=ROOT/'build/session-logs'/('wifi-scan-'+marker[-16:]);private_write(prefix.with_suffix('.console.private.txt'),res.stdout+res.stderr)
 if res.returncode:raise RuntimeError('scan snapshot failed')
 data,analysis=parse(res.stdout.decode('ascii'),marker);private_write(prefix.with_suffix('.private.bin'),data);private_write(prefix.with_suffix('.analysis.json'),(json.dumps(analysis,indent=2)+'\n').encode());print(json.dumps({'private_prefix':str(prefix),'analysis':analysis}))
if __name__=='__main__':main()

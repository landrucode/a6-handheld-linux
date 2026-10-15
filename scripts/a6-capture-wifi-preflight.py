#!/usr/bin/env python3
"""Read retained regulatory preflight replies; never submit firmware commands."""
from pathlib import Path
import base64,json,re,secrets,subprocess,sys,hashlib,os
ROOT=Path(__file__).resolve().parents[1]
BASE='/sys/firmware/a6_wifi_ehci_enum'
def parse(console,marker):
 lines=console.replace('\r','').splitlines();begin,end=marker+'_BEGIN',marker+'_END'
 if lines.count(begin)!=1 or lines.count(end)!=1:raise ValueError('ambiguous snapshot markers')
 first,last=lines.index(begin),lines.index(end)
 if first>=last:raise ValueError('reversed markers')
 statuses=[l for l in lines[:first] if l.startswith('A6_WIFI_USB_PREFLIGHT_V1 ')]
 if len(statuses)!=1:raise ValueError('ambiguous status')
 f=dict(re.findall(r'(\w+)=([^ ]+)',statuses[0]))
 for key,val in [('enabled','1'),('attempted','1'),('radio_up','0'),('bulk_out','0')]:
  if f.get(key)!=val:raise ValueError('preflight safety/status mismatch')
 country=f.get('country_trial_enabled','0')
 if country not in ('0','1'):raise ValueError('invalid country mode')
 limit=9 if country=='1' else 4
 if not 0<=int(f['set'])<=(2 if country=='1' else 0):raise ValueError('unbounded SETs')
 if not 0<=int(f['rx'])<=limit or not 0<=int(f['tx'])<=limit:raise ValueError('unbounded controls')
 data=base64.b64decode(''.join(lines[first+1:last]),validate=True)
 if len(data)>1120:raise ValueError('snapshot too large')
 cursor=0;records=[];previous=3
 while cursor<len(data):
  if len(data)-cursor<4:raise ValueError('truncated record')
  id=int.from_bytes(data[cursor:cursor+2],'little');n=int.from_bytes(data[cursor+2:cursor+4],'little');cursor+=4
  if not previous<id<=(12 if country=='1' else 7) or n>276 or n>len(data)-cursor:raise ValueError('invalid record')
  record=data[cursor:cursor+n];records.append({'request_id':id,'bytes':n,'sha256':hashlib.sha256(record).hexdigest()});previous=id;cursor+=n
 if len(records)>int(f['rx']):raise ValueError('record count exceeds replies')
 return data,{'status':f,'records':records,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def private_write(p,data):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data)
 p.chmod(0o400)
def main():
 marker='A6_PREF_'+secrets.token_hex(8);emit=lambda value:"printf '%s%s\\n' "+value[:len(value)//2]+' '+value[len(value)//2:]
 command=f'cat {BASE}/preflight; '+emit(marker+'_BEGIN')+f'; busybox base64 {BASE}/preflight_data; '+emit(marker+'_END')
 result=subprocess.run([sys.executable,str(ROOT/'scripts/a6-usb-acm-direct.py'),command,'--until',marker+'_END','--timeout','20'],capture_output=True,timeout=30)
 prefix=ROOT/'build/session-logs'/('wifi-preflight-'+marker[-16:]);private_write(prefix.with_suffix('.console.private.txt'),result.stdout+result.stderr)
 if result.returncode:raise RuntimeError('preflight snapshot read failed')
 data,summary=parse(result.stdout.decode('ascii'),marker);private_write(prefix.with_suffix('.private.bin'),data)
 private_write(prefix.with_suffix('.analysis.json'),(json.dumps(summary,indent=2)+'\n').encode())
 print(json.dumps({'private_prefix':str(prefix),'analysis':summary}))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Execute GB SET/readback/restore actual C, with ambiguous application faults."""
from pathlib import Path
import runpy,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
base=runpy.run_path(str(ROOT/'scripts/test-a6-wifi-usb-preflight.py'))
harness=base['harness'].split('static int usb_control_msg(')[0]+r'''
static unsigned char original[12]={'X','Z',0,0,9,0,0,0,'X','Z',0,0},current[12];
static unsigned fail_id,fail_direction,corrupt_restore,wrong_country,reply_set;
static int usb_control_msg(struct usb_device*d,int pipe,int req,int type,int v,int idx,void *buf,int n,int timeout){
 unsigned char*p=buf;calls++;assert(!v&&!idx&&timeout==1000);
 if(!pipe){
  assert(req==0&&type==33);cmd=get_unaligned_le32(p);id=get_unaligned_le32(p+8)>>16;
  assert(id>=4&&id<=12&&get_unaligned_le32(p+4)==(unsigned)n-16&&!get_unaligned_le32(p+12));
  bool set=id==8||id==11;
  assert(cmd==(set?263:id==7||id==10?217:262));assert(get_unaligned_le32(p+8)==((id<<16)|(set?2:0)));
  if(set){
   assert(n==36&&!strcmp((char*)p+16,"country"));
   if(id==8){assert(!memcmp(p+24,"GB\0\0",4)&&get_unaligned_le32(p+28)==~0U&&!memcmp(p+32,"GB\0\0",4));}
   else assert(!memcmp(p+24,original,12));
   memcpy(current,p+24,12);if(id==8)put_unaligned_le32(0,current+4);
  }
  if(id==fail_id&&fail_direction==0)return -ETIMEDOUT;return n;
 }
 assert(req==1&&type==161&&pipe==128);
 if(id==fail_id&&fail_direction==128)return -ETIMEDOUT;
 put_unaligned_le32(cmd,p);put_unaligned_le32((id<<16)|((id==8||id==11)&&reply_set?2:0),p+8);
 if(id==8||id==11){put_unaligned_le32(20,p+4);return 36;}
 unsigned reported=id==5?8:id==6?6:id==7||id==10?16:12;
 put_unaligned_le32(reported,p+4);
 if(id==4||id==9||id==12){memcpy(p+16,current,12);if(id==9&&wrong_country)p[16]='X';if(id==12&&corrupt_restore)p[20]^=1;}
 if(id==5)memcpy(p+16,"testclm",8);
 if(id==6){p[16]=2;p[21]=1;}
 if(id==7||id==10){put_unaligned_le32(3,p+16);put_unaligned_le32(1,p+20);put_unaligned_le32(6,p+24);put_unaligned_le32(11,p+28);}
 return n;
}
'''
main=r'''
static void reset(void){assert(!live);memcpy(current,original,12);memset(a6_pref_data,0,sizeof(a6_pref_data));
 a6_pref_attempted=a6_pref_tx=a6_pref_rx=a6_pref_bytes=0;a6_pref_result=-EAGAIN;
 a6_country_attempted=a6_country_sets=a6_country_gb_channels=0;a6_country_result=a6_country_restore=-EAGAIN;
 allocations=fail_alloc=calls=fail_id=fail_direction=corrupt_restore=wrong_country=reply_set=unlocks=0;lock_available=1;a6_runtime_result=0;a6_runtime_completed=3;
}
int main(void){struct usb_device d;char b[4096];
 reset();a6_trial_preflight(&d);assert(!a6_pref_result&&!a6_country_result&&!a6_country_restore&&a6_country_attempted&&a6_country_sets==2&&a6_country_gb_channels==3);
 assert(a6_pref_tx==9&&a6_pref_rx==9&&a6_pref_bytes<=1120&&!memcmp(current,original,12)&&!live&&unlocks==1);
 a6_ehci_preflight(b);assert(strstr(b,"country_trial_enabled=1")&&strstr(b,"set=2"));
 reset();reply_set=1;a6_trial_preflight(&d);assert(!a6_country_result&&!a6_country_restore);
 a6_trial_preflight(&d);assert(a6_pref_result==-EPERM&&a6_country_sets==2);
 for(unsigned failure=8;failure<=12;failure++)for(unsigned direction=0;direction<=128;direction+=128){
  reset();fail_id=failure;fail_direction=direction;a6_trial_preflight(&d);assert(!live&&unlocks==1);
  if(failure<=10){assert(a6_country_result==-ETIMEDOUT&&!a6_country_restore&&!memcmp(current,original,12));}
  else assert(a6_country_restore==-ETIMEDOUT);
 }
 reset();wrong_country=1;a6_trial_preflight(&d);assert(a6_country_result==-EPROTO&&!a6_country_restore&&!memcmp(current,original,12));
 reset();corrupt_restore=1;a6_trial_preflight(&d);assert(!a6_country_result&&a6_country_restore==-EUCLEAN);
 for(unsigned failure=1;failure<=9;failure++){
  reset();fail_alloc=failure;a6_trial_preflight(&d);assert(!live&&unlocks==1);
  if(failure<=4)assert(!a6_country_attempted&&!a6_country_sets);
  else if(failure<=7)assert(a6_country_result==-ENOMEM&&!a6_country_restore&&!memcmp(current,original,12));
  else assert(a6_country_restore==-ENOMEM);
 }
 puts("PASS actual GB unspecified-revision SET/readback/channel query/original full restore, ambiguous SET failures, allocation/one-shot guards and restore mismatch refusal; no UP/scan");
}
'''
with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
 p=Path(td);(p/'test.c').write_text(harness+base['source']+main)
 subprocess.run(['cc','-DA6_WIFI_USB_COUNTRY=1','-fsanitize=address,undefined','-g','-O1',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
# Exercise real private-parser and collector country classifications.
import base64,sys,contextlib,io
private,m=base['private'],base['m']
status=base['status'].replace('tx=4 rx=4','tx=9 rx=9').replace('set=0','set=2')+' country_trial_enabled=1 country_attempted=1 country_result=0 country_restore=0 gb_channels=3'
journal=b''.join(i.to_bytes(2,'little')+(16).to_bytes(2,'little')+bytes(16) for i in range(4,13))
console=status+'\nP_BEGIN\n'+base64.b64encode(journal).decode()+'\nP_END\n'
assert private.parse(console,'P')[0]==journal
for old,new in [('set=2','set=3'),('rx=9','rx=10'),('tx=9','tx=10'),('radio_up=0','radio_up=1'),('country_trial_enabled=1','country_trial_enabled=0')]:
 try:private.parse(console.replace(old,new),'P')
 except ValueError:pass
 else:raise AssertionError('unbounded country capture accepted')
full=base['scope']['prefix']+base['scope']['status']+status+'\n'
assert m.classify_preflight(full,country=True)=='firmware_country_readbacks_original_restored'
assert m.classify_preflight(full.replace('country_restore=0','country_restore=-121'),country=True)=='firmware_country_restore_unverified'
assert m.classify_preflight(full.replace('country_result=0','country_result=-121'),country=True)=='firmware_country_not_proven'
assert m.classify_preflight(full)=='firmware_preflight_incomplete_restored'
pre=base['pre'].replace('enabled=1 attempted=0 \n','enabled=1 attempted=0 country_trial_enabled=1 country_attempted=0 \n')
commands=[]
def serial(command,timeout=20):
 commands.append(command);return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial;old=sys.argv
try:
 sys.argv=['collector','--preflight']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:assert str(e)=='Country-enabled image requires explicit --country; no trial submitted'
 else:raise AssertionError('implicit country SET accepted')
 assert len(commands)==1 and '> $b/run' not in commands[0]
finally:sys.argv=old
print('PASS country private journal bounds, restored/unverified classification and explicit --country before writer')

#!/usr/bin/env python3
"""Run actual USB scan controller with transport, clock and cleanup faults."""
from pathlib import Path
import runpy,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
base=runpy.run_path(str(ROOT/'scripts/test-a6-wifi-usb-bulk-rx.py'))
h=base['harness'].split('static int usb_bulk_msg(')[0]+r'''
#include <stdarg.h>
#define USB_DIR_OUT 0
#define USB_DIR_IN 128
#define USB_TYPE_CLASS 32
#define USB_RECIP_INTERFACE 1
static unsigned long jiffies;
#define msecs_to_jiffies(x) (x)
#define jiffies_to_msecs(x) (x)
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
static unsigned a6_runtime_ioctl=1;
static int sysfs_emit(char*b,const char*f,...){va_list a;va_start(a,f);int n=vsprintf(b,f,a);va_end(a);return n;}
static unsigned usb_sndctrlpipe(struct usb_device*d,unsigned ep){assert(!ep);return 0;}
static unsigned usb_rcvctrlpipe(struct usb_device*d,unsigned ep){assert(!ep);return 128;}
static unsigned char country[12],events[32];
static unsigned reqid,cmd,capacity,fail_id,fail_dir,fail_mode,seen[64],nseen,rx_mode;
static unsigned reads,radio,started,mpc;
static unsigned little(const unsigned char*p,unsigned n){unsigned v=0;for(unsigned i=0;i<n;i++)v|=(unsigned)p[i]<<(i*8);return v;}
static void put(unsigned char*p,unsigned v,unsigned n){for(unsigned i=0;i<n;i++)p[i]=v>>(i*8);}
static int usb_control_msg(struct usb_device*d,unsigned pipe,int request,int type,int v,int idx,void*buf,int n,int timeout){
 unsigned char*p=buf;assert(locks&&registered&&owned&&!v&&!idx&&timeout==1000);jiffies++;
 if(!pipe){
  assert(!request&&type==33);cmd=little(p,4);capacity=little(p+4,4);reqid=little(p+8,4)>>16;seen[nseen++]=reqid;
  assert(reqid>=20&&reqid<=39&&capacity==(unsigned)n-16&&!little(p+12,4));
  unsigned set=little(p+8,4)&2;
  if(set){
   assert(cmd==263||cmd==2||cmd==3);
   if(reqid==29||reqid==34){assert(!strcmp((char*)p+16,"mpc"));mpc=little(p+20,4);}
   if(reqid==24||reqid==38){assert(!strcmp((char*)p+16,"country"));memcpy(country,p+24,12);if(reqid==24){assert(little(country+4,4)==~0U);put(country+4,28,4);}}
   if(reqid==27||reqid==36){assert(!strcmp((char*)p+16,"event_msgs"));memcpy(events,p+27,32);}
   if(reqid==30){assert(cmd==2&&little(p+16,4)==1);radio=1;}
   if(reqid==33){assert(cmd==3&&little(p+16,4)==1);radio=0;}
   if(reqid==31){assert(cmd==263&&!strcmp((char*)p+16,"escan")&&radio&&country[0]=='G'&&events[8]&32&&!mpc);assert(p[22+51]==1&&!little(p+22+52,4));started=1;}
   if(reqid==32){assert(!strcmp((char*)p+16,"escan")&&little(p+26,2)==3);started=0;}
  }else assert(cmd==262||cmd==217);
  /* SET application precedes injected OUT failure, exercising ambiguity. */
  if(reqid==fail_id&&fail_dir==0)return -ETIMEDOUT;
  return n;
 }
 assert(pipe==128&&request==1&&type==161);
 if(reqid==fail_id&&fail_dir==128&&fail_mode==0)return -ETIMEDOUT;
 put(p,cmd,4);put(p+4,capacity,4);put(p+8,reqid<<16,4);
 if(reqid==20||reqid==25||reqid==39)memcpy(p+16,country,12);
 if(reqid==21||reqid==28||reqid==37)memcpy(p+16,events,32);
 if(reqid==23||reqid==35)put(p+16,mpc,4);
 if(reqid==22){p[16]=2;p[21]=1;}
 if(reqid==26){put(p+16,3,4);put(p+20,1,4);put(p+24,6,4);put(p+28,11,4);}
 if(reqid==fail_id&&fail_dir==128){
  if(fail_mode==1)p[8]^=4;
  if(fail_mode==2)put(p+12,~0U,4);
  if(fail_mode==3)return 15;
  if(fail_mode==4){if(reqid==25||reqid==39)p[16]^=1;else if(reqid==28||reqid==37)p[16]^=1;else put(p+4,~0U,4);}
 }
 return n;
}
static void be(unsigned char*p,unsigned v,unsigned n){for(unsigned i=0;i<n;i++)p[n-i-1]=v>>(i*8);}
static int usb_bulk_msg(struct usb_device*d,unsigned pipe,void*buf,int n,int*actual,int timeout){
 assert(locks&&registered&&owned&&radio&&started&&pipe==0x81&&n==2048&&timeout>0&&timeout<=3000);bulk_calls++;unsigned char*p=buf;memset(p,0,n);
 if(rx_mode==1){jiffies+=timeout;*actual=0;return -ETIMEDOUT;}
 if(rx_mode==2||rx_mode==3){jiffies+=rx_mode==2?10:1000;*actual=4;return 0;}
 p[0]=0x20;p[16]=0x88;p[17]=0x6c;p[18]=0x80;p[19]=1;p[24]=0x10;p[25]=0x18;p[27]=1;p[29]=2;be(p+32,69,4);
 if(reads++==0){
  be(p+36,8,4);be(p+48,144,4);unsigned char*q=p+76;put(q,144,4);put(q+4,109,4);put(q+8,0x1234,2);put(q+10,1,2);put(q+12,109,4);put(q+16,132,4);put(q+128,128,2);put(q+132,4,4);q[140]=0;q[141]=2;q[142]='a';q[143]='b';*actual=220;
  if(rx_mode==4)put(q+8,0x4321,2);
 }else {*actual=76;started=0;}
 jiffies+=10;return 0;
}
'''
# Existing actual endpoint and event helpers, omitting the ordinary trial runner.
helpers=base['functions'].split('static void a6_trial_bulk_rx(')[0]
source=(ROOT/'kernel/platform/a6-wifi-usb-scan.inc').read_text().replace('#include "a6-wifi-scan-codec.h"',(ROOT/'kernel/platform/a6-wifi-scan-codec.h').read_text())
setup=base['main'].split('int main(')[0]
main=r'''
static void reset(void){init();jiffies=nseen=reads=radio=started=fail_id=fail_dir=fail_mode=rx_mode=0;
 a6_scan_attempted=a6_scan_tx=a6_scan_rx=a6_scan_receives=a6_scan_partials=a6_scan_complete=a6_scan_other=a6_scan_used=a6_scan_up_attempted=a6_scan_country_attempted=a6_scan_mask_attempted=a6_scan_start_attempted=0;
 a6_scan_result=a6_scan_abort=a6_scan_down=a6_scan_mask_restore=a6_scan_country_restore=a6_scan_mpc_restore=-EAGAIN;a6_scan_mpc_attempted=0;mpc=1;
 memset(country,0,12);country[0]=country[8]='X';country[1]=country[9]='Z';put(country+4,9,4);memset(events,0,32);events[0]=7;
}
static bool has(unsigned id){for(unsigned i=0;i<nseen;i++)if(seen[i]==id)return true;return false;}
static void restored(void){cleaned();assert(!radio&&country[0]=='X'&&little(country+4,4)==9&&mpc==1&&events[0]==7&&!events[8]);}
int main(void){char status[4096];
 reset();a6_trial_preflight(&dev);restored();assert(!a6_scan_result&&!a6_scan_down&&!a6_scan_mask_restore&&!a6_scan_country_restore&&a6_scan_complete&&a6_scan_partials==1&&!has(32));
 a6_ehci_preflight(status);assert(strstr(status,"association=0 bulk_out=0"));assert(a6_scan_used<136000);unsigned n=nseen;a6_trial_preflight(&dev);restored();assert(!a6_scan_result&&nseen>n&&a6_scan_attempted==2);
 for(unsigned id=20;id<=39;id++)for(unsigned dir=0;dir<=128;dir+=128){
  reset();fail_id=id;fail_dir=dir;rx_mode=1;a6_trial_preflight(&dev);cleaned();
  if(id<=31){assert(a6_scan_result<0);restored();}
  if(has(24))assert(has(38));if(has(27))assert(has(36)&&has(38));if(has(30))assert(has(33)&&has(36)&&has(38));if(has(31))assert(has(32));
 }
 for(unsigned id=20;id<=39;id++)for(unsigned mode=1;mode<=4;mode++){
  reset();fail_id=id;fail_dir=128;fail_mode=mode;rx_mode=1;a6_trial_preflight(&dev);cleaned();
  if(id<=31)restored();if(has(30))assert(has(33)&&has(38));
 }
 for(unsigned mode=1;mode<=4;mode++){reset();rx_mode=mode;a6_trial_preflight(&dev);restored();assert(a6_scan_receives<=64);if(mode==2)assert(a6_scan_result==-ENOSPC&&a6_scan_receives==64);if(mode==3)assert(a6_scan_receives==3);if(mode==4)assert(a6_scan_partials==0&&a6_scan_complete);}
 reset();alloc_fail=1;a6_trial_preflight(&dev);cleaned();assert(!nseen&&a6_scan_result==-ENOMEM);
 reset();claim_fail=-EBUSY;a6_trial_preflight(&dev);cleaned();assert(!nseen);
 reset();lock_available=0;a6_trial_preflight(&dev);cleaned();assert(!nseen);
 reset();a6_runtime_ioctl=2;a6_trial_preflight(&dev);assert(!nseen&&a6_scan_result==-EPERM);a6_runtime_ioctl=1;
 reset();release_fail=1;a6_trial_preflight(&dev);assert(a6_rx_release==-EUCLEAN);cleaned();
 puts("PASS actual scan controller: every OUT/IN/header/status/short/mismatch fault, ambiguous SET/UP, all subsequent cleanup, claim/allocation/lock/release/one-shot guards; partial/stale/completion/deadline/receive cap; repeat attempts in one boot; MPC off/restore; no association/data OUT");
}
'''
with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
 p=Path(td);(p/'test.c').write_text(h+base['decls']+helpers+source+setup+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g','-O1',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
import importlib.util,base64,struct,sys,contextlib,io
spec=importlib.util.spec_from_file_location('snapshot',ROOT/'scripts/a6-capture-wifi-scan.py');capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
m=base['m']
status='A6_WIFI_USB_SCAN_V1 enabled=1 attempted=1 result=0 tx=15 rx=15 receives=2 partials=1 complete=1 other=0 abort=0 down=0 mask_restore=0 country_restore=0 release=0 registered=1 deregistered=1 bytes=40 up_attempted=1 country_attempted=1 mask_attempted=1 start_attempted=1 mpc_restore=0 mpc_attempted=1 gb_revision=28 passive=1 association=0 bulk_out=0'
journal=struct.pack('<HHI',20,16,1)+bytes(16)+struct.pack('<HHI',0x8000,8,2)+bytes(8)
console=status+'\nM_BEGIN\n'+base64.b64encode(journal).decode()+'\nM_END\n'
assert capture.parse(console,'M')[0]==journal
for old,new in [('tx=15','tx=24'),('receives=2','receives=65'),('bytes=40','bytes=40001'),('association=0','association=1'),('bulk_out=0','bulk_out=1')]:
 try:capture.parse(console.replace(old,new),'M')
 except ValueError:pass
 else:raise AssertionError('unsafe snapshot accepted')
full=base['prefix']+status+'\n'
assert m.classify_scan(full)=='firmware_scan_BSS_observed_restored'
assert m.classify_scan(full.replace('partials=1','partials=0'))=='firmware_scan_completion_only_restored'
for key in ('abort','down','mask_restore','country_restore','mpc_restore','release'):
 assert m.classify_scan(full.replace(key+'=0',key+'=-110'))=='firmware_scan_cleanup_unverified'
pre=base['pre']+'A6_WIFI_USB_SCAN_V1 enabled=1 attempted=0 \n';commands=[]
def serial(command,timeout=20):commands.append(command);return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial;old=sys.argv
try:
 sys.argv=['collector','--rx']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:assert str(e)=='Scan-enabled image requires explicit --scan; no trial submitted'
 else:raise AssertionError('implicit scan accepted')
 assert len(commands)==1 and '> $b/run' not in commands[0]
finally:sys.argv=old
assert len(m.build_capture_command('/tmp/a6-ehci-'+'0'*16,True,True,True,True,True,True,False,True).encode())<=900
print('PASS scan snapshot bounds/privacy, completion versus BSS/cleanup classifications, explicit --scan guard and shell-line bound')

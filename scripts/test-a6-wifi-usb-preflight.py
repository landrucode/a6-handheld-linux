#!/usr/bin/env python3
"""Execute actual four-GET preflight and private snapshot reader under sanitizers."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'kernel/platform/a6-wifi-usb-preflight.inc').read_text()
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <sys/types.h>
#include <stdarg.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t u32;
#define A6_WIFI_USB_PREFLIGHT 1
#define GFP_KERNEL 0
#define USB_DIR_OUT 0
#define USB_DIR_IN 128
#define USB_TYPE_CLASS 32
#define USB_RECIP_INTERFACE 1
struct usb_device {int unused;};
static int a6_runtime_result;static unsigned a6_runtime_completed=3;
static unsigned allocations,live,fail_alloc,calls,fail_call,id,cmd,unlocks,lock_available=1,mode;
static int injected=-ETIMEDOUT;
static void *kzalloc(unsigned n,int f){if(++allocations==fail_alloc)return NULL;void *p=calloc(1,n);if(p)live++;return p;}
static void kfree(void *p){if(p){assert(live);live--;free(p);}}
static unsigned get_unaligned_le32(const void *p){const unsigned char*b=p;return b[0]|((u32)b[1]<<8)|((u32)b[2]<<16)|((u32)b[3]<<24);}
static void put_unaligned_le32(u32 v,void *p){unsigned char*b=p;for(unsigned i=0;i<4;i++)b[i]=v>>(8*i);}
static int sysfs_emit(char*b,const char*f,...){va_list a;va_start(a,f);int n=vsnprintf(b,4096,f,a);va_end(a);return n;}
#define usb_sndctrlpipe(d,e) 0
#define usb_rcvctrlpipe(d,e) 128
static int usb_trylock_device(struct usb_device*d){return lock_available;}
static void usb_unlock_device(struct usb_device*d){unlocks++;}
static int usb_control_msg(struct usb_device*d,int pipe,int req,int type,int v,int idx,void *buf,int n,int timeout){
 unsigned char*p=buf;calls++;assert(!v&&!idx&&timeout==1000);
 if(pipe==0){
  assert(req==0&&type==33);cmd=get_unaligned_le32(p);id=get_unaligned_le32(p+8)>>16;
  assert(id>=4&&id<=7&&get_unaligned_le32(p+8)==id<<16&&!get_unaligned_le32(p+12));
  unsigned sizes[]={28,272,32,276};assert((unsigned)n==sizes[id-4]&&get_unaligned_le32(p+4)==(unsigned)n-16);
  assert(cmd==(id==7?217:262));
  const char *names[]={"country","clmver","cur_etheraddr"};
  if(id<7)assert(!strcmp((char*)p+16,names[id-4]));else assert(get_unaligned_le32(p+16)==64);
  if(calls==fail_call)return injected;return n;
 }
 assert(pipe==128&&req==1&&type==161);
 for(unsigned i=0;i<(unsigned)n;i++)assert(!p[i]);
 if(calls==fail_call&&mode==0)return injected;
 put_unaligned_le32(cmd,p);put_unaligned_le32(id<<16,p+8);
 unsigned reported=id==4?12:id==5?8:id==6?6:16;
 if(id==4){memcpy(p+16,"GB",3);put_unaligned_le32(~0U,p+20);memcpy(p+24,"GB",3);}
 if(id==5)memcpy(p+16,"testclm",8);
 if(id==6){p[16]=2;p[21]=1;}
 if(id==7){put_unaligned_le32(3,p+16);put_unaligned_le32(1,p+20);put_unaligned_le32(6,p+24);put_unaligned_le32(11,p+28);}
 put_unaligned_le32(reported,p+4);
 if(calls==fail_call)switch(mode){
 case 1:p[0]^=1;break;case 2:p[10]^=1;break;case 3:p[8]=2;break;
 case 4:p[8]=1;put_unaligned_le32(~0U,p+12);break;
 case 5:put_unaligned_le32(n,p+4);break;
 case 6:put_unaligned_le32(1,p+4);break;
 case 7:memset(p+16,'X',n-16);break;
 case 8:put_unaligned_le32(65,p+16);break;
 case 9:put_unaligned_le32(0,p+20);break;
 case 10:p[16]=1;break;
 case 11:memset(p+16,0,6);break;
 }
 return 16+reported;
}
'''
main=r'''
static void reset(void){assert(!live);a6_pref_attempted=a6_pref_tx=a6_pref_rx=a6_pref_bytes=0;a6_pref_result=-EAGAIN;
 for(unsigned i=0;i<4;i++)a6_pref_query_result[i]=-EAGAIN;
 a6_pref_country_gb=a6_pref_clm_bytes=a6_pref_mac_valid=a6_pref_channels=0;
 allocations=fail_alloc=calls=fail_call=unlocks=mode=0;lock_available=1;a6_runtime_result=0;a6_runtime_completed=3;injected=-ETIMEDOUT;
}
int main(void){struct usb_device d;char buf[4096];
 reset();a6_trial_preflight(&d);assert(!a6_pref_result&&calls==8&&unlocks==1&&!live);
 assert(a6_pref_country_gb&&a6_pref_clm_bytes==7&&a6_pref_mac_valid&&a6_pref_channels==3);
 assert(a6_pref_tx==4&&a6_pref_rx==4&&a6_runtime_completed==3&&a6_pref_bytes==122);
 for(unsigned off=0;off<=1121;off++){ssize_t n=a6_ehci_preflight_data(buf,off,sizeof(buf));assert(n==(off<122?122-off:0));if(n)assert(!memcmp(buf,a6_pref_data+off,n));}
 assert(a6_ehci_preflight_data(buf,-1,1)==-EINVAL);
 assert(a6_ehci_preflight_data(buf,0,0)==0);
 a6_ehci_preflight(buf);assert(strstr(buf,"radio_up=0 set=0 bulk_out=0"));
 a6_trial_preflight(&d);assert(a6_pref_result==-EPERM&&calls==8);
 for(unsigned failure=1;failure<=4;failure++){reset();fail_alloc=failure;a6_trial_preflight(&d);assert(a6_pref_result==-ENOMEM&&a6_pref_tx==3&&a6_pref_rx==3&&!live&&unlocks==1);}
 for(unsigned call=1;call<=8;call++){reset();fail_call=call;a6_trial_preflight(&d);assert(a6_pref_result==-ETIMEDOUT&&!live&&unlocks==1);}
 unsigned sizes[]={28,272,32,276};
 for(unsigned q=0;q<4;q++)for(unsigned len=0;len<=sizes[q]+1;len++){
  if(len==sizes[q])continue;reset();fail_call=q*2+1;injected=len;a6_trial_preflight(&d);assert(a6_pref_query_result[q]==-EMSGSIZE&&!live&&unlocks==1);
 }
 for(unsigned q=0;q<4;q++)for(unsigned len=0;len<16;len++){
  reset();fail_call=q*2+2;injected=len;a6_trial_preflight(&d);assert(a6_pref_query_result[q]==-EMSGSIZE&&!live);
 }
 for(unsigned q=0;q<4;q++)for(unsigned error=1;error<=5;error++){
  reset();fail_call=q*2+2;mode=error;a6_trial_preflight(&d);assert(a6_pref_query_result[q]<0&&!live&&unlocks==1);
 }
 for(unsigned q=0;q<4;q++){if(q==1)continue;reset();fail_call=q*2+2;mode=6;a6_trial_preflight(&d);assert(a6_pref_query_result[q]<0);}
 for(unsigned q=0;q<2;q++){reset();fail_call=q*2+2;mode=7;a6_trial_preflight(&d);assert(a6_pref_query_result[q]<0);}
 for(unsigned error=8;error<=9;error++){reset();fail_call=8;mode=error;a6_trial_preflight(&d);assert(a6_pref_query_result[3]<0);}
 for(unsigned error=10;error<=11;error++){reset();fail_call=6;mode=error;a6_trial_preflight(&d);assert(!a6_pref_query_result[2]&&!a6_pref_mac_valid);}
 reset();lock_available=0;a6_trial_preflight(&d);assert(a6_pref_result==-EBUSY&&!calls&&!unlocks);
 reset();a6_runtime_result=-EIO;a6_trial_preflight(&d);assert(a6_pref_result==-EPERM&&!calls);
 reset();a6_runtime_completed=2;a6_trial_preflight(&d);assert(a6_pref_result==-EPERM&&!calls);
 assert(a6_pref_query(&d,4)==-EINVAL&&!calls);
 puts("PASS actual four-GET preflight: fixed wire whitelist/no SET/UP, private bounded journal/reader, malformed/unsupported replies, identity/string/channel bounds, allocations, locking and one-shot guards");
}
'''
with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
 p=Path(td);(p/'test.c').write_text(harness+source+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g','-O1',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
import importlib.util,base64,re,sys,contextlib,io
spec=importlib.util.spec_from_file_location('private',ROOT/'scripts/a6-capture-wifi-preflight.py');private=importlib.util.module_from_spec(spec);spec.loader.exec_module(private)
status='A6_WIFI_USB_PREFLIGHT_V1 enabled=1 attempted=1 result=0 tx=4 rx=4 country=0 clm=0 mac=0 channels=0 country_gb=1 clm_bytes=7 mac_valid=1 channel_count=3 radio_up=0 set=0 bulk_out=0'
journal=b''.join(i.to_bytes(2,'little')+(16).to_bytes(2,'little')+bytes(16) for i in range(4,8))
console=status+'\nP_BEGIN\n'+base64.b64encode(journal).decode()+'\nP_END\n'
assert private.parse(console,'P')[0]==journal
for bad in (journal[:-1],journal+b'\0',journal+ journal,journal[:2]+(277).to_bytes(2,'little')+journal[4:]):
 try:private.parse(console.replace(base64.b64encode(journal).decode(),base64.b64encode(bad).decode()),'P')
 except ValueError:pass
 else:raise AssertionError('malformed journal accepted')
for old,new in [('set=0','set=1'),('radio_up=0','radio_up=1'),('bulk_out=0','bulk_out=1'),('rx=4','rx=5'),('attempted=1','attempted=0')]:
 try:private.parse(console.replace(old,new),'P')
 except ValueError:pass
 else:raise AssertionError('unsafe status accepted')
spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/a6-capture-wifi-ehci-enum.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
other=(ROOT/'scripts/test-a6-wifi-usb-runtime.py').read_text();a=other.index("base='A6_WIFI_EHCI_ENUM");b=other.index('assert m.classify_runtime',a);scope={};exec(other[a:b],scope)
full=scope['prefix']+scope['status']+status+'\n'
assert m.classify_preflight(full)=='firmware_preflight_readbacks_restored'
assert m.classify_preflight(full.replace('country=0','country=-121'))=='firmware_preflight_query_failure_restored'
assert m.classify_preflight(full.replace('set=0','set=1'))=='firmware_preflight_incomplete_restored'
# Actual CLI refuses implicit use before firmware transfer writer is submitted.
pre=('auto=1 paused=0 fault=0 attached=1\nA6_LOW_BATTERY_CANDIDATE_V3 enabled=1 attended_trial=0 attended_plugged=0 threshold_mv=3600\n'
'A6_WIFI_EHCI_ENUM_V2 attempted=0 \nA6_EHCI_PROGRESS_V1 phase=0 \nA6_WIFI_USB_IDENTITY_V1 enabled=1 \nA6_WIFI_USB_OTP_V1 enabled=1 \nA6_WIFI_USB_DOWNLOAD_V1 enabled=1 \nA6_WIFI_USB_EXECUTE_V1 enabled=1 \nA6_WIFI_USB_RUNTIME_V1 enabled=1 \nA6_WIFI_USB_PREFLIGHT_V1 enabled=1 attempted=0 \n')
commands=[]
def serial(command,timeout=20):commands.append(command);return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial;original=sys.argv
try:
 sys.argv=['collector','--runtime']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:assert str(e)=='Preflight image requires explicit --preflight; no trial submitted'
 else:raise AssertionError('implicit preflight accepted')
 assert len(commands)==1 and '> $b/run' not in commands[0]
 assert len((commands[0]+"; echo A6_ENUM_END_0000000000000000\n").encode())<1024
finally:sys.argv=original
cmd=m.build_capture_command('/tmp/a6-ehci-'+'0'*16,True,True,True,True,True,False,False,True)
assert '$b/preflight' in cmd and len(cmd.encode())<=900
print('PASS private reply capture bounds/markers/safety, collector classifications and explicit activation before one-shot')

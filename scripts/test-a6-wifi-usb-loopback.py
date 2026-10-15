#!/usr/bin/env python3
"""Exercise actual bounded loopback code, including ambiguous SET and cleanup failures."""
from pathlib import Path
import subprocess, tempfile, sys
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'kernel/platform/a6-wifi-usb-loopback.inc').read_text()
rx=(ROOT/'kernel/platform/a6-wifi-usb-bulk-rx.inc').read_text()
helpers=rx[rx.index('static unsigned int a6_rx_layout_byte'):rx.index('#ifdef A6_WIFI_USB_LOOPBACK\nstatic void a6_rx_inspect')]+rx[rx.index('static noinline int a6_rx_unwrap_kind'):rx.index('/* BCDC data header:')]
decls=s[s.index('static int a6_loop_result'):s.index('ssize_t a6_ehci_loopback(char *buf)\n{')]
code=s[s.index('/* Fixed iovar'):s.rindex('#endif')]
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <stdio.h>
typedef uint32_t u32; typedef uint8_t u8; typedef uint16_t u16;
#define GFP_KERNEL 0
#define noinline __attribute__((noinline))
#define USB_DIR_OUT 0
#define USB_DIR_IN 128
#define USB_TYPE_CLASS 32
#define USB_RECIP_INTERFACE 1
struct usb_device {int unused;};
static int a6_runtime_result,a6_rx_usb_result;
static unsigned a6_runtime_completed=3,a6_rx_frames=1,a6_rx_event_type=52;
static unsigned char a6_rx_snapshot[32864];
static unsigned a6_rx_snapshot_bytes;
static unsigned a6_rx_out=2,a6_rx_in=0x81,a6_rx_wrapper_bytes,a6_rx_tx;
static unsigned mode,id,cmd,fail_id,fail_direction,outs,ins,trace_count,rx_kind;
static int scenario;
static unsigned long jiffies;
static unsigned packet_ms=50,allocation_calls,allocation_fail,live_allocations;
#define msecs_to_jiffies(n) (n)
#define jiffies_to_msecs(n) (n)
#define time_after_eq(a,b) ((long)((a)-(b))>=0)

static unsigned char sent[96],private_packet[3][2048];
static unsigned private_length[3];
static void *kzalloc(unsigned n,int flag){if(++allocation_calls==allocation_fail)return NULL;void *p=calloc(1,n);if(p)live_allocations++;return p;}
static void kfree(void *p){if(p){assert(live_allocations);live_allocations--;free(p);}}
static u32 get_unaligned_le32(const void *p){u32 v;memcpy(&v,p,4);return v;}
static void put_unaligned_le32(u32 v,void *p){memcpy(p,&v,4);}
#define usb_sndctrlpipe(d,e) 0
#define usb_rcvctrlpipe(d,e) 128
#define usb_sndbulkpipe(d,e) (e)
#define usb_rcvbulkpipe(d,e) ((e)|128)
static int usb_control_msg(struct usb_device *d,int pipe,int req,int type,int value,int index,void *buf,int size,int timeout){
 unsigned char *p=buf;
 assert(!value&&!index&&timeout==1000);
 if(!pipe){
  assert(req==0&&type==33);cmd=get_unaligned_le32(p);id=get_unaligned_le32(p+8)>>16;
  assert(!memcmp(p+16,"bus:loopback",13));
  assert((cmd==262&&size==48&&(id==4||id==7))||(cmd==263&&size==33&&(id==5||id==6)));
  if(cmd==263){mode=get_unaligned_le32(p+29);assert(mode==(id==5));}
 }else{
  assert(req==1&&type==161);put_unaligned_le32(cmd,p);put_unaligned_le32(cmd==262?4:0,p+4);
  put_unaligned_le32(id<<16,p+8);put_unaligned_le32(0,p+12);put_unaligned_le32(mode,p+16);
 }
 if(id==fail_id&&pipe==fail_direction)return -ETIMEDOUT;
 return pipe?(cmd==262?20:16):size;
}
static void wrap(unsigned char *p,unsigned total){
 unsigned sum=0;memset(p,0,16);p[0]=0x11;p[1]=0x80|(rx_kind<<4);p[4]=total;p[5]=total>>8;
 for(unsigned i=0;i<16;i+=2)sum+=p[i]|(p[i+1]<<8);
 sum=(sum&65535)+(sum>>16);sum=(~sum)&65535;p[2]=sum;p[3]=sum>>8;
}
static int usb_bulk_msg(struct usb_device *d,unsigned pipe,void *buf,int size,int *actual,int timeout){
 unsigned char *p=buf;assert(timeout>=1&&timeout<=2000);
 if(pipe==2){
 unsigned sum=0;for(unsigned i=0;i<16;i+=2)sum+=p[i]|(p[i+1]<<8);
 sum=(sum&65535)+(sum>>16);sum=(sum&65535)+(sum>>16);
#ifdef A6_WIFI_USB_LOOPBACK_BAD_CHECKSUM
 assert(sum!=65535);
#else
 assert(sum==65535);
#endif
 outs++;assert(size==96&&p[0]==1&&p[1]==0xa0&&p[16]==0x20&&!memcmp(p+26,"A6USBLOOP02!",12));memcpy(sent,p,96);*actual=scenario==1?95:96;return 0;}
 assert(pipe==0x81&&size==2048);
 assert((uintptr_t)p<(uintptr_t)a6_rx_snapshot || (uintptr_t)p>=(uintptr_t)a6_rx_snapshot+sizeof(a6_rx_snapshot));
 for(unsigned z=0;z<2048;z++)assert(p[z]==0);ins++;
 if(packet_ms>(unsigned)timeout){jiffies+=timeout;return -ETIMEDOUT;}jiffies+=packet_ms;
 if(scenario==2)return -ETIMEDOUT;
 if(scenario==6){*actual=2049;return 0;}
 if(scenario==7){*actual=0;return 0;}
 if(ins<=trace_count){
  if(ins<=3&&private_length[ins-1]){memcpy(p,private_packet[ins-1],private_length[ins-1]);*actual=private_length[ins-1];return 0;}
  wrap(p,92);p[16]=0x20;p[32]=0x88;p[33]=0x6c;p[34]=0x80;p[35]=1;
  p[40]=0x10;p[41]=0x18;p[43]=1;p[45]=2;p[51]=scenario==5?53:52;*actual=92;
  if(scenario==9){memmove(p,p+16,76);*actual=76;}return 0;
 }
 memcpy(p+16,sent+16,80);wrap(p,96);*actual=96;
 if(scenario==10){memmove(p,p+16,80);*actual=80;}
 if(scenario==3)p[30]^=1;
 if(scenario==4)p[2]^=1;
 return 0;
}
'''
main=r'''
static void reset(void){
 assert(!live_allocations);allocation_calls=allocation_fail=0;
 a6_loop_result=a6_loop_restore=-EAGAIN;a6_loop_attempted=a6_loop_ctl_tx=a6_loop_ctl_rx=0;
 a6_loop_out=a6_loop_in=a6_loop_echo=a6_loop_skipped=a6_loop_other=a6_loop_before=a6_loop_after=a6_loop_bytes=0;
 a6_rx_snapshot_bytes=0;memset(a6_rx_snapshot,0,32864);
 mode=id=cmd=fail_id=fail_direction=outs=ins=trace_count=a6_rx_tx=rx_kind=0;scenario=0;jiffies=0;packet_ms=50;
}
int main(int argc,char **argv){struct usb_device d;
 for(unsigned kind=0;kind<=2;kind+=2)for(unsigned traces=0;traces<=16;traces++){
  reset();rx_kind=kind;trace_count=traces;int ret=a6_trial_loopback(&d);
  assert(mode==0&&outs==1&&ins==(traces<16?traces+1:16)&&a6_loop_restore==0);
  assert(a6_rx_snapshot_bytes==(traces<16?traces*98+102:1568)&&a6_loop_bytes==a6_rx_snapshot_bytes);
  for(unsigned packet=0;packet<(traces<16?traces+1:16);packet++){
   unsigned cursor=packet*98;unsigned length=a6_rx_snapshot[cursor]|(a6_rx_snapshot[cursor+1]<<8);
   assert(length==(packet<traces?92:96));assert(get_unaligned_le32(a6_rx_snapshot+cursor+2)==(packet+1)*50);
   if(packet==traces)assert(!memcmp(a6_rx_snapshot+cursor+22,sent+16,80));
  }
  assert(ret==(traces<16?0:-ENOMSG));assert(a6_loop_echo==(traces<16));
  assert(a6_trial_loopback(&d)==-EPERM&&outs==1);
 }
 reset();scenario=9;trace_count=3;assert(a6_trial_loopback(&d)==0);
 assert(ins==4&&a6_loop_skipped==3&&a6_loop_echo&&a6_rx_snapshot_bytes==348);
 reset();scenario=10;assert(a6_trial_loopback(&d)==-ENOMSG);
 assert(ins==16&&!a6_loop_echo&&a6_loop_other==16&&a6_rx_snapshot_bytes==1376);
 reset();jiffies=~0UL-1000;assert(a6_trial_loopback(&d)==0&&ins==1);
 reset();trace_count=16;packet_ms=600;assert(a6_trial_loopback(&d)==-ETIMEDOUT);
 assert(ins==4&&jiffies==2000&&a6_loop_skipped==3&&a6_rx_snapshot_bytes==294&&a6_loop_restore==0);
 for(unsigned kind=1;kind<=7;kind++){
  if(kind==2)continue;reset();rx_kind=kind;assert(a6_trial_loopback(&d)==-ENOMSG);
  assert(ins==16&&a6_loop_other==16&&!a6_loop_echo&&a6_loop_restore==0);
 }
 for(unsigned kind=0;kind<=7;kind++){
  unsigned char header[80]={0};rx_kind=kind;wrap(header,80);const unsigned char *frame=header;unsigned n=80;
  assert(a6_rx_unwrap(&frame,&n)==(kind==0?0:-EPROTO));
 }
 for(int test=1;test<=4;test++){
  reset();scenario=test;assert(a6_trial_loopback(&d)<0);assert(mode==0&&a6_loop_restore==0&&outs==1&&!a6_loop_echo);
  assert(a6_rx_snapshot_bytes==(test>=3?16*102:0));
 }
 reset();rx_kind=2;scenario=5;trace_count=1;assert(a6_trial_loopback(&d)==0);
 assert(ins==2&&a6_loop_other==1&&a6_loop_skipped==0&&a6_rx_snapshot_bytes==200&&a6_loop_restore==0);
 reset();scenario=6;assert(a6_trial_loopback(&d)==-EMSGSIZE&&!a6_rx_snapshot_bytes&&a6_loop_restore==0);
 reset();scenario=7;assert(a6_trial_loopback(&d)==-ENOMSG&&a6_rx_snapshot_bytes==96&&a6_loop_restore==0);
 for(unsigned stage=4;stage<=7;stage++)for(unsigned dir=0;dir<=128;dir+=128){
  reset();fail_id=stage;fail_direction=dir;assert(a6_trial_loopback(&d)==-ETIMEDOUT);
  if(stage==4)assert(!outs&&!ins&&a6_loop_ctl_tx==1);
  if(stage==5)assert(!outs&&!ins&&mode==0&&a6_loop_restore==0);
  if(stage>=6)assert(outs==1&&a6_loop_echo&&a6_loop_restore==-ETIMEDOUT);
 }
 for(unsigned fail=1;fail<=5;fail++){
  reset();allocation_fail=fail;assert(a6_trial_loopback(&d)==-ENOMEM);
  assert(!live_allocations);
  if(fail<=3)assert(!outs&&!ins);
  if(fail==3)assert(mode==0&&a6_loop_restore==0);
  if(fail>=4)assert(a6_loop_restore==-ENOMEM);
 }
 reset();mode=1;assert(a6_trial_loopback(&d)==-EBUSY&&!outs);
 reset();a6_runtime_completed=2;assert(a6_trial_loopback(&d)==-EPERM&&!a6_loop_attempted);
 assert(a6_loop_control(&d,8,true,1,NULL)==-EINVAL);
 unsigned char built[96]={0};assert(brcmf_a6_hsic_tx_header(built,80,2)==0);built[16]=0x20;memcpy(built+26,"A6USBLOOP02!",12);for(unsigned i=38;i<96;i++)built[i]=i^0xa5;
#ifdef A6_WIFI_USB_LOOPBACK_BAD_CHECKSUM
 built[2]^=1;
#endif
 assert(!memcmp(built,sent,96));
 if(argc==3||argc==4){
  unsigned count=argc-1,total=102,cursor=0;
  for(unsigned packet=0;packet<count;packet++){
   FILE *file=fopen(argv[packet+1],"rb");assert(file);private_length[packet]=fread(private_packet[packet],1,2048,file);fclose(file);
   assert(private_length[packet]==(packet==2?162:178));total+=private_length[packet]+6;
  }
  reset();a6_runtime_completed=3;trace_count=count;assert(a6_trial_loopback(&d)==0);
  assert(a6_loop_skipped==count&&ins==count+1&&outs==1&&a6_loop_echo&&a6_rx_snapshot_bytes==total);
  for(unsigned packet=0;packet<count;packet++){
   assert(!memcmp(a6_rx_snapshot+cursor+6,private_packet[packet],private_length[packet]));cursor+=private_length[packet]+6;
  }
  puts("PASS private wrapped/bare TRACE replay plus synthetic echo; hardware echo unproven");
 }
 puts("PASS actual loopback deadline2000ms/cap16, arrival journal, unknown-packet retention, strict echo/TRACE and cleanup");
}
'''

replays = [Path(arg).resolve() for arg in sys.argv[1:]]
if replays and (len(replays) not in (2,3) or any(not p.is_relative_to(ROOT/'build') for p in replays)):
 raise ValueError('private replay requires two or three ignored build/ packets')
with tempfile.TemporaryDirectory(prefix='a6-loop-',dir=ROOT/'build') as temp:
 p=Path(temp);(p/'test.c').write_text(harness+(ROOT/'kernel/platform/brcmfmac-a6-hsic.h').read_text()+decls+helpers+code+main)
 for negative in (False, True):
  subprocess.run(['cc','-fsanitize=address,undefined','-g','-O1']+(['-DA6_WIFI_USB_LOOPBACK_BAD_CHECKSUM=1'] if negative else [])+[str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')]+[str(packet) for packet in replays],check=True)
import importlib.util, sys, contextlib, io
sp=importlib.util.spec_from_file_location('capture',ROOT/'scripts/a6-capture-wifi-ehci-enum.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
other=(ROOT/'scripts/test-a6-wifi-usb-runtime.py').read_text();a=other.index("base='A6_WIFI_EHCI_ENUM");b=other.index('assert m.classify_runtime',a)
exec(other[a:b],globals());prefix+=status
bulk='A6_WIFI_USB_BULK_RX_V1 enabled=1 result=0 attempted=1 usb_result=0 registered=1 deregistered=1 claimed=1 disconnected=1 release=0 submitted=1 bytes=178 in=81 out=02 mps=512 frames=1 payload=158 tx=1\n'
loop='A6_WIFI_USB_LOOPBACK_V1 enabled=1 result=0 restore=0 attempted=1 ctl_tx=4 ctl_rx=4 out=1 in=1 echo=1 skipped=0 other=0 before=0 after=0 bytes=86 radio_up=0\n'
assert m.classify_loopback(prefix+bulk+loop)=='bulk_loopback_echo_observed_restored'
for old,new in [('echo=1','echo=0'),('out=1','out=2'),('in=1','in=17'),('skipped=0','skipped=1'),('after=0','after=1'),('ctl_rx=4','ctl_rx=3'),('radio_up=0','radio_up=1')]:
 assert m.classify_loopback(prefix+bulk+loop.replace(old,new))=='bulk_loopback_not_proven_restored'
assert m.classify_loopback(prefix+bulk+loop.replace('restore=0','restore=-110'))=='bulk_loopback_not_proven_restore_unverified'
assert m.classify_loopback(prefix+bulk.replace('release=0','release=-5')+loop)=='bulk_rx_driver_release_unverified'
pre=('auto=1 paused=0 fault=0 attached=1\nA6_LOW_BATTERY_CANDIDATE_V3 enabled=1 attended_trial=0 attended_plugged=0 threshold_mv=3600\n'
 'A6_WIFI_EHCI_ENUM_V2 attempted=0 \nA6_EHCI_PROGRESS_V1 phase=0 \n'
 'A6_WIFI_USB_IDENTITY_V1 enabled=1 \nA6_WIFI_USB_OTP_V1 enabled=1 \nA6_WIFI_USB_DOWNLOAD_V1 enabled=1 \n'
 'A6_WIFI_USB_EXECUTE_V1 enabled=1 \nA6_WIFI_USB_RUNTIME_V1 enabled=1 \nA6_WIFI_USB_BULK_RX_V1 enabled=1 \nA6_WIFI_USB_LOOPBACK_V1 enabled=1 \n')
commands=[]
def serial(command,timeout=20):commands.append(command);return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial;original=sys.argv
try:
 sys.argv=['collector','--rx']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:assert str(e)=='Loopback-enabled image requires explicit --loopback; no trial submitted'
 else:raise AssertionError('implicit loopback accepted')
 assert len(commands)==1 and '/run;' not in commands[0]
 assert len((commands[0]+"; printf '%s%s\\n' A6_ENUM_END_000 0000000000000\n").encode())<1024
finally:sys.argv=original
print('PASS loopback collector: strict evidence, restoration/lifecycle failures and refusal of implicit activation')

import re
assert not re.search(r'(?m)^trial_inflight=1\r?$', 'echo trial_inflight=1; fi;\n')
assert re.search(r'(?m)^trial_inflight=1\r?$', 'echo command\ntrial_inflight=1\r\n')
assert "not re.search(r'(?m)^trial_inflight=1" in (ROOT/'scripts/a6-capture-wifi-ehci-enum.py').read_text()
print('PASS automatic capture ignores echoed shell text and recognizes standalone in-flight status')

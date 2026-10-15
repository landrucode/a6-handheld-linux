#!/usr/bin/env python3
"""Execute actual BCDC runtime helpers with wire/reply/fault controls."""
from pathlib import Path
import subprocess,tempfile,importlib.util,re
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'kernel/platform/a6-wifi-usb-runtime.inc').read_text();s=s[s.index('static int a6_runtime_query('):s.rindex('#endif')]
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t u32;typedef uint16_t u16;typedef uint32_t __le32;
#define cpu_to_le32(x) (x)
#define le32_to_cpu(x) (x)
#define le16_to_cpu(x) (x)
#define GFP_KERNEL 0
#define USB_STATE_CONFIGURED 7
#define USB_DIR_OUT 0
#define USB_DIR_IN 128
#define USB_TYPE_CLASS 32
#define USB_RECIP_INTERFACE 1
#define WRITE_ONCE(x,v) ((x)=(v))
struct alt {struct {unsigned bInterfaceNumber;} desc;};
struct intf {struct alt *cur_altsetting;};
struct config {struct {unsigned bNumInterfaces;} desc;struct intf *interface[1];};
struct usb_device {unsigned state;struct {unsigned idVendor,idProduct;} descriptor;struct config *actconfig;};
static int a6_runtime_result,a6_execute_result,a6_trial_phase,a6_runtime_tx_length,a6_runtime_rx_length;
static u32 a6_runtime_last_command,a6_runtime_reply_flags,a6_runtime_reply_status,a6_runtime_reply_length;
static unsigned a6_runtime_tx,a6_runtime_rx,a6_runtime_completed;
static u32 a6_runtime_ioctl,a6_runtime_chip,a6_runtime_chiprev,a6_runtime_version_bytes,a6_execute_chip;
static unsigned calls,allocs,fail_alloc,unlocks,locked,fail_call,mode;
static u32 cmd,id;static int injected;
static void *kzalloc(unsigned n,int flag){return ++allocs==fail_alloc?NULL:calloc(1,n);}
#define kfree free
static int usb_trylock_device(struct usb_device*d){return locked;}
static void usb_unlock_device(struct usb_device*d){unlocks++;}
static unsigned usb_sndctrlpipe(struct usb_device*d,int ep){assert(ep==0);return 0;}
static unsigned usb_rcvctrlpipe(struct usb_device*d,int ep){assert(ep==0);return 128;}
static int usb_control_msg(struct usb_device*d,unsigned pipe,int req,int type,int value,int index,void *buf,int n,int timeout){
 __le32 *m=buf;assert(value==0&&index==0&&timeout==1000);calls++;
 if(req==0){assert(pipe==0&&type==0x21);cmd=m[0];id=m[2]>>16;assert(m[2]==id<<16&&m[1]==(unsigned)n-16&&!m[3]);
 assert((cmd==1&&id==1&&n==20)||(cmd==98&&id==2&&n==84)||(cmd==262&&id==3&&n==272));
 if(cmd==262)assert(!memcmp(m+4,"ver",4));
 if(calls==fail_call)return injected;return n;}
 assert(req==1&&pipe==128&&type==0xa1);
 if(calls==fail_call&&mode==0)return injected;
 m[0]=cmd;m[1]=n-16;m[2]=id<<16;m[3]=0;
 if(cmd==1)m[4]=2;
 if(cmd==98){m[4+3]=3;m[4+11]=0x4334;}
 if(cmd==262)memcpy(m+4,"BCM4334 test firmware",22);
 if(calls==fail_call){switch(mode){
 case 1:m[0]++;break;case 2:m[2]^=1U<<16;break;case 3:m[2]|=1;break;case 4:m[3]=1;break;
 case 5:m[1]=n;break;case 6:m[1]=1;m[4]=99;break;case 7:m[4+11]=0;break;case 8:m[4+3]=0;break;
 case 12:m[4+11]=4334;break;case 13:m[4]=1;break;
 case 9:memset(m+4,'x',n-16);break;case 10:((unsigned char*)(m+4))[0]=0;break;case 11:((unsigned char*)(m+4))[0]=255;break;
 }}return n;
}
'''
main=r'''
static struct alt a={{0}};static struct intf i={&a};static struct config c={{1},{&i}};
static struct usb_device d={7,{0xa5c,0xbd1a},&c};
static void init(void){a6_runtime_result=-EAGAIN;a6_execute_result=0;a6_execute_chip=0xa123;
 a6_runtime_tx=a6_runtime_rx=a6_runtime_completed=0;a6_runtime_ioctl=a6_runtime_chip=a6_runtime_chiprev=a6_runtime_version_bytes=0;
 calls=allocs=fail_alloc=unlocks=fail_call=mode=0;locked=1;d.state=7;d.actconfig=&c;c.desc.bNumInterfaces=1;a.desc.bInterfaceNumber=0;d.descriptor.idProduct=0xbd1a;}
int main(void){
 init();a6_trial_runtime_probe(&d);assert(a6_runtime_result==0&&calls==6&&unlocks==1&&a6_runtime_tx==3&&a6_runtime_rx==3&&a6_runtime_completed==3&&a6_runtime_chip==0x4334&&a6_runtime_chiprev==3&&a6_runtime_ioctl==2&&a6_runtime_version_bytes==21);
 a6_trial_runtime_probe(&d);assert(a6_runtime_result==-EPERM&&calls==6); /* consumed */
 for(unsigned call=1;call<=6;call++)for(int len=-32;len<273;len++){
  int good=call<=2?20:call<=4?84:272;if(len==good)continue;
  init();fail_call=call;injected=len;a6_trial_runtime_probe(&d);assert(a6_runtime_result<0&&calls==call&&unlocks==1);
 }
 for(unsigned error=1;error<=5;error++)for(unsigned call=2;call<=6;call+=2){init();fail_call=call;mode=error;a6_trial_runtime_probe(&d);assert(a6_runtime_result<0&&calls==call);}
 for(unsigned error=6;error<=11;error++){init();mode=error;fail_call=error==6?2:error<=8?4:6;a6_trial_runtime_probe(&d);assert(a6_runtime_result<0&&calls==fail_call);}
 init();mode=12;fail_call=4;a6_trial_runtime_probe(&d);assert(a6_runtime_result==-EPROTO&&calls==4); /* reject decimal chip4334 */
 init();mode=13;fail_call=2;a6_trial_runtime_probe(&d);assert(a6_runtime_result==0&&a6_runtime_ioctl==1); /* measured ioctl1 */
 for(unsigned failure=1;failure<=4;failure++){init();fail_alloc=failure;a6_trial_runtime_probe(&d);assert(a6_runtime_result==-ENOMEM&&calls<=4);}
 for(unsigned guard=0;guard<7;guard++){init();switch(guard){case 0:a6_execute_result=-5;break;case 1:a6_execute_chip=0;break;case 2:locked=0;break;case 3:d.state=0;break;case 4:d.actconfig=NULL;break;case 5:c.desc.bNumInterfaces=2;break;case 6:a.desc.bInterfaceNumber=1;break;}a6_trial_runtime_probe(&d);assert(a6_runtime_result<0&&calls==0);}
 init();d.descriptor.idProduct=1;a6_trial_runtime_probe(&d);assert(a6_runtime_result<0&&calls==0);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(harness+s+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual BCDC helpers: six wire transfers, bounded GET allowlist, short/error replies, malformed headers/IDs/status, identity/version, allocation/locking/consumption guards')
sp=importlib.util.spec_from_file_location('capture',ROOT/'scripts/a6-capture-wifi-ehci-enum.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
# Independent synthetic classification fixture.
base='A6_WIFI_EHCI_ENUM_V2 attempted=1 result=0 restore=0 stage=4 vid=0a5c reset72=09 reset72_after=09 reset_readback=0 gate_before=00000200 gate_after=00000200 phy8=0 phy8_after=0 usb_ctl=c0000080 usb_ctl_after=c0000080 pmu_submitted=2 pmu_completed=2 pmu_restore_submitted=1 pmu_restore_completed=1\n'
identity='A6_WIFI_USB_IDENTITY_V1 enabled=1 result=0 length=24 submitted=1 fields=3f request=05 type=c1 value=0001 index=0000 chip=00004334 chiprev=00000003 ramsize=00080000 remapbase=60000000\n'
otp='A6_WIFI_USB_OTP_V1 enabled=1 result=0 submitted=127 completed=127 bytes=250 start=64 end=314 request=11 type=c1 reply_bytes=16 data_word=3 data='+('00'*250)+'\n'
download='A6_WIFI_USB_DOWNLOAD_V1 enabled=1 result=0 bulk_submitted=305 bulk_completed=305 control_submitted=3 control_completed=3 sent=456108 expected=456108 state=4 rom_bytes=456108 endpoint=03 go_submitted=0\n'
execution='A6_WIFI_USB_EXECUTE_V1 enabled=1 result=0 go_submitted=1 go_completed=1 reset=-19 getver_submitted=1 getver_length=24 chip=0000a123 gpio_writes=4 gpio_saved=00000202 gpio_after=00000202 gpio_restore=0\n'
prefix=base+identity+otp+download+execution
status='A6_WIFI_USB_RUNTIME_V1 enabled=1 result=0 tx=3 rx=3 completed=3 ioctl=2 chip=17204 chiprev=3 version_bytes=20 inactive_resumes=5\n'
assert m.classify_runtime(prefix+status)=='firmware_runtime_transport_hsic_restored'
assert m.classify_runtime(prefix+status+'port 4 resume error -110\n')=='firmware_runtime_transport_passed_hsic_errors_restored'
for old,new in [('result=0','result=-5'),('tx=3','tx=4'),('rx=3','rx=2'),('chip=17204','chip=1'),('completed=3','completed=2')]:
 assert m.classify_runtime(prefix+status.replace(old,new))=='firmware_runtime_transport_failed_restored'
for old,new in [('ioctl=2','ioctl=0'),('version_bytes=20','version_bytes=0')]:
 assert m.classify_runtime(prefix+status.replace(old,new))=='firmware_runtime_transport_invalid_restored'
print('PASS runtime collector requires accepted startup/restoration, exact command counts, runtime chip/revision/version and no HSIC errors')

# Exercise actual preflight: runtime firmware needs an explicit runtime mode.
import sys,contextlib,io
pre=('auto=1 paused=0 fault=0 attached=1\n'
     'A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 attended_trial=0 attended_plugged=0 threshold_mv=3600\n'
     'A6_WIFI_EHCI_ENUM_V2 attempted=0 \nA6_EHCI_PROGRESS_V1 phase=0 \n'
     'A6_WIFI_USB_IDENTITY_V1 enabled=1 \nA6_WIFI_USB_OTP_V1 enabled=1 \n'
     'A6_WIFI_USB_DOWNLOAD_V1 enabled=1 \nA6_WIFI_USB_EXECUTE_V1 enabled=1 \n'
     'A6_WIFI_USB_RUNTIME_V1 enabled=1 \n')
commands=[]
def serial(command,timeout=20):
 commands.append(command);return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial;original=sys.argv
try:
 sys.argv=['collector','--execute']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:assert str(e)=='Runtime-enabled image requires explicit --runtime; no trial submitted'
 else:raise AssertionError('implicit runtime accepted')
 assert len(commands)==1 and '/run;' not in commands[0] and '/run ' not in commands[0]
 assert len((commands[0]+"; printf '%s%s\\n' A6_ENUM_END_000 0000000000000\n").encode())<1024
finally:sys.argv=original
print('PASS actual collector preflight rejects runtime image without --runtime before one-shot')

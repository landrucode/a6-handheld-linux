#!/usr/bin/env python3
"""Execute actual GPIO/GO/reset/runtime helpers with fault injection."""
from pathlib import Path
import subprocess, tempfile, importlib.util
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'kernel/platform/a6-wifi-usb-download.inc').read_text()
a=s.index('static int a6_execute_level(');functions=s[a:s.index('\n#endif',a)]
harness=r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t u32;typedef uint32_t __le32;
#define GFP_KERNEL 0
#define USB_STATE_CONFIGURED 7
#define USB_DIR_IN 128
#define USB_TYPE_VENDOR 64
#define USB_RECIP_INTERFACE 1
#define A6_WIFI_FW_BYTES 456108
#define WRITE_ONCE(x,y) ((x)=(y))
#define le16_to_cpu(x) (x)
#define le32_to_cpu(x) (x)
struct usb_device {int state;struct {int idVendor,idProduct;} descriptor;};
static int a6_download_result,a6_trial_phase,a6_execute_result,a6_execute_reset,a6_execute_restore,a6_execute_length;
static unsigned a6_download_state,a6_download_sent,a6_download_rom_bytes,a6_download_completed,a6_download_submitted;
static unsigned a6_execute_go,a6_execute_go_completed,a6_execute_getver,a6_execute_writes;
static u32 a6_execute_saved,a6_execute_after,a6_execute_chip;
static unsigned char *a6_execute_gpio;
static unsigned char region[4096];
static unsigned writes,fail_write,commands,resets,allocs,fail_alloc,sleeps,unlocks;
static int locked,map_fail,go_reply,query_reply,reset_reply;static u32 query_chip;
static int usb_trylock_device(struct usb_device*d){return locked;}
static void usb_unlock_device(struct usb_device*d){unlocks++;}
static void *kzalloc(size_t n,int f){return ++allocs==fail_alloc?NULL:calloc(1,n);}
#define kfree free
static void *ioremap(unsigned base,unsigned len){assert(base==0x3fa00000 && len==4096);return map_fail?NULL:region;}
static void iounmap(void*p){assert(p==region);}
static void writel(u32 v,void*p){assert(p==region+0xd8);writes++;if(writes!=fail_write)memcpy(p,&v,4);}
static u32 readl(void*p){u32 v;assert(p==region+0xd8);memcpy(&v,p,4);return v;}
static void msleep(unsigned n){assert(n==20||n==500);sleeps+=n;}
static unsigned usb_rcvctrlpipe(struct usb_device*d,int n){assert(n==0);return 128;}
static int usb_control_msg(struct usb_device*d,unsigned pipe,int req,int type,int value,int index,void *buf,int n,int timeout){
 assert(pipe==128 && type==0xc1 && value==1 && index==0 && timeout==1000);commands++;
 if(req==2){assert(n==8 && a6_execute_go==1 && readl(region+0xd8)==0x203);return go_reply;}
 assert(req==5 && n==24 && a6_execute_getver==1);memcpy(buf,&query_chip,4);return query_reply;
}
static int usb_reset_device(struct usb_device*d){assert(readl(region+0xd8)==0x203);resets++;return reset_reply;}
'''
main=r'''
static struct usb_device d={7,{0xa5c,0xbd1a}};
static void init(void){
 memset(region,0,sizeof(region));u32 v=0x202;memcpy(region+0xd8,&v,4);
 a6_execute_gpio=NULL;a6_execute_result=a6_execute_reset=a6_execute_restore=-EAGAIN;a6_execute_length=-1;
 a6_execute_go=a6_execute_go_completed=a6_execute_getver=a6_execute_writes=0;
 a6_execute_saved=a6_execute_after=a6_execute_chip=0;
 a6_download_result=0;a6_download_state=4;a6_download_sent=a6_download_rom_bytes=456108;
 a6_download_submitted=a6_download_completed=305;writes=fail_write=commands=resets=allocs=fail_alloc=sleeps=unlocks=0;
 locked=1;map_fail=0;go_reply=8;query_reply=24;reset_reply=-ENODEV;query_chip=0xa123;d.state=7;d.descriptor.idProduct=0xbd1a;
}
static void restore(void){a6_trial_execute_restore();assert(a6_execute_gpio==NULL);assert(readl(region+0xd8)==0x202);}
int main(void){
 init();a6_trial_execute(&d);assert(a6_execute_result==-EAGAIN && commands==1 && resets==1 && writes==3 && sleeps==560);
 a6_trial_runtime_identity(&d);assert(a6_execute_result==0 && commands==2);restore();assert(a6_execute_restore==0 && writes==4);
 for(int n=-32;n<9;n++){if(n==8)continue;init();go_reply=n;a6_trial_execute(&d);assert(a6_execute_result!=0 && a6_execute_go==1 && !resets && commands==1);restore();}
 for(int n=-32;n<=28;n++){init();a6_trial_execute(&d);query_reply=n;a6_trial_runtime_identity(&d);assert((a6_execute_result==0)==(n>=8&&n<=24&&n%4==0));restore();}
 for(int n=1;n<=3;n++){init();fail_write=n;a6_trial_execute(&d);assert(a6_execute_result==-EIO && !resets);assert(commands==(n==1?0:1));restore();}
 init();a6_trial_execute(&d);fail_write=4;a6_trial_execute_restore();assert(a6_execute_restore==-EUCLEAN && readl(region+0xd8)==0x203);
 init();reset_reply=-EIO;a6_trial_execute(&d);assert(a6_execute_result==-EIO && resets==1);restore();
 init();a6_trial_execute(&d);query_chip=0x4334;a6_trial_runtime_identity(&d);assert(a6_execute_result==-EPROTO);restore();
 for(int n=0;n<7;n++){init();switch(n){case 0:a6_download_result=-EIO;break;case 1:a6_download_state=1;break;case 2:a6_download_sent--;break;case 3:a6_download_rom_bytes--;break;case 4:a6_download_completed--;break;case 5:a6_download_submitted++;break;case 6:locked=0;break;}a6_trial_execute(&d);assert(!commands&&!writes&&!resets);}
 init();fail_alloc=1;a6_trial_execute(&d);assert(a6_execute_result==-ENOMEM && !writes);restore();
 init();map_fail=1;a6_trial_execute(&d);assert(a6_execute_result==-ENOMEM && !writes);restore();
 init();u32 v=0xffff0202;memcpy(region+0xd8,&v,4);a6_trial_execute(&d);assert(a6_execute_result==-EUCLEAN&&!writes);a6_trial_execute_restore();assert(readl(region+0xd8)==v);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=Path(td);(p/'test.c').write_text(harness+functions+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g','-O1',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS actual execution helpers: GO/GETVER lengths/errors, GPIO writes/restoration, reset/refusal/allocation guards')
spec=importlib.util.spec_from_file_location('capture',ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
# Keep classification fixtures independent of hardware/private records.
base='A6_WIFI_EHCI_ENUM_V2 attempted=1 result=0 restore=0 stage=4 vid=0a5c reset72=09 reset72_after=09 reset_readback=0 gate_before=00000200 gate_after=00000200 phy8=0 phy8_after=0 usb_ctl=c0000080 usb_ctl_after=c0000080 pmu_submitted=2 pmu_completed=2 pmu_restore_submitted=1 pmu_restore_completed=1\n'
identity='A6_WIFI_USB_IDENTITY_V1 enabled=1 result=0 length=24 submitted=1 fields=3f request=05 type=c1 value=0001 index=0000 chip=00004334 chiprev=00000003 ramsize=00080000 remapbase=60000000\n'
otp='A6_WIFI_USB_OTP_V1 enabled=1 result=0 submitted=127 completed=127 bytes=250 start=64 end=314 request=11 type=c1 reply_bytes=16 data_word=3 data='+('00'*250)+'\n'
download='A6_WIFI_USB_DOWNLOAD_V1 enabled=1 result=0 bulk_submitted=305 bulk_completed=305 control_submitted=3 control_completed=3 sent=456108 expected=456108 state=4 rom_bytes=456108 endpoint=03 go_submitted=0\n'
execution='A6_WIFI_USB_EXECUTE_V1 enabled=1 result=0 go_submitted=1 go_completed=1 reset=-19 getver_submitted=1 getver_length=24 chip=0000a123 gpio_writes=4 gpio_saved=00000202 gpio_after=00000202 gpio_restore=0\n'
prefix=base+identity+otp+download
assert m.classify_execute(prefix+execution)=='firmware_runtime_identity_restored'
for old,new in [('go_submitted=1','go_submitted=2'),('go_completed=1','go_completed=0'),('reset=-19','reset=-5'),('getver_submitted=1','getver_submitted=2'),('getver_length=24','getver_length=4'),('chip=0000a123','chip=00004334'),('gpio_writes=4','gpio_writes=3')]:
 assert m.classify_execute(prefix+execution.replace(old,new))=='firmware_execution_invalid_restored'
assert m.classify_execute(prefix+execution.replace('gpio_restore=0','gpio_restore=-5'))=='firmware_execution_gpio_restoration_failed'
assert m.classify_execute(prefix+execution.replace('gpio_after=00000202','gpio_after=00000203'))=='firmware_execution_gpio_restoration_failed'
assert m.classify_execute(prefix+execution.replace('result=0','result=-110'))=='firmware_execution_failed_restored'
print('PASS collector requires one GO, verified runtime response and GPIO/platform restoration')
# Execute the real preflight orchestration. A download-only invocation must
# refuse an execution image without sending the one-shot command.
import sys, contextlib, io
pre=('auto=1 paused=0 fault=0 attached=1\n'
     'A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 attended_trial=0 attended_plugged=0 threshold_mv=3600\n'
     'A6_WIFI_EHCI_ENUM_V2 attempted=0 \nA6_EHCI_PROGRESS_V1 phase=0 \n'
     'A6_WIFI_USB_IDENTITY_V1 enabled=1 \nA6_WIFI_USB_OTP_V1 enabled=1 \n'
     'A6_WIFI_USB_DOWNLOAD_V1 enabled=1 \nA6_WIFI_USB_EXECUTE_V1 enabled=1 \n')
commands=[]
def serial(command,timeout=20):
 commands.append(command)
 return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial
original=sys.argv
try:
 sys.argv=['collector','--download']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:
  assert str(e)=='Execution-enabled image requires explicit --execute; no trial submitted'
 else:raise AssertionError('execution image accepted without explicit mode')
 assert len(commands)==1 and '/run;' not in commands[0] and '/run ' not in commands[0]
 assert len((commands[0]+"; printf '%s%s\\n' A6_ENUM_END_000 0000000000000\n").encode())<1024
finally:sys.argv=original
print('PASS actual collector preflight refuses execution image in download-only mode before one-shot')

assert m.classify_execute(prefix+execution.replace('result=0','result=-110').replace('getver_submitted=1','getver_submitted=0'))=='firmware_reenumeration_timeout_restored'
print('PASS re-enumeration timeout classification distinguishes completed GO from missing runtime observation')

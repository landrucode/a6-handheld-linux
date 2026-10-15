#!/usr/bin/env python3
"""Execute the candidate GETVER function with mocked USB replies and refusals."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
s = (root/'kernel/platform/ehci-a6-trial.c').read_text()
a = s.index('static void a6_trial_get_identity(')
b = s.index('\n#endif', a)
function = s[a:b]
harness = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t __le32;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,y) ((x)=(y))
#define BIT(i) (1U<<(i))
#define GFP_KERNEL 0
#define USB_STATE_CONFIGURED 7
#define USB_DIR_IN 0x80
#define USB_TYPE_VENDOR 0x40
#define USB_RECIP_INTERFACE 1
#define pr_info(...) ((void)0)
#define le16_to_cpu(x) (x)
#define le32_to_cpu(x) (x)
struct alt { struct { int bInterfaceNumber; } desc; };
struct interface { struct alt *cur_altsetting; };
struct config { struct { int bNumInterfaces; } desc; struct interface *interface[1]; };
struct usb_device { int state; struct { int idVendor, idProduct; } descriptor; struct config *actconfig; };
static int a6_identity_result, a6_identity_length, a6_trial_phase;
static unsigned a6_identity_submitted, a6_identity_fields;
static uint32_t a6_identity_words[6];
static int response, locked=1, alloc_fail, unlocks;
static uint32_t wire[6]={0x4334,2,0x80000,0,0x1234,0x10};
static int usb_trylock_device(struct usb_device *d) { return locked; }
static void usb_unlock_device(struct usb_device *d) { unlocks++; }
static void *kzalloc(size_t n,int flags) { return alloc_fail ? NULL : calloc(1,n); }
#define kfree free
static unsigned usb_rcvctrlpipe(struct usb_device *d,int n) { assert(n==0); return 0x80; }
static int usb_control_msg(struct usb_device *d,unsigned pipe,int req,int type,int value,int index,void *buffer,int size,int ms) {
 assert(pipe==0x80 && req==5 && type==0xc1 && value==1 && index==0 && size==24 && ms==2000);
 if(response>0) memcpy(buffer,wire,response>24 ? 24 : response);
 return response;
}
'''
main=r'''
static void reset(void) { a6_identity_result=-EAGAIN; a6_identity_length=-1;
a6_identity_submitted=a6_identity_fields=unlocks=alloc_fail=0; locked=1; memset(a6_identity_words,0,sizeof(a6_identity_words)); }
int main(void) {
 struct alt alt={.desc={0}};struct interface iface={&alt};
 struct config cfg={.desc={1},.interface={&iface}};
 struct usb_device dev={.state=7,.descriptor={0x0a5c,0xbd1a},.actconfig=&cfg};
 for(int len=0;len<=28;len++) {
 reset();response=len;a6_trial_get_identity(&dev);
 bool valid=len>=8 && len<=24 && len%4==0;
 assert(a6_identity_result==(valid ? 0 : -EMSGSIZE));
 assert(a6_identity_length==len && a6_identity_submitted==1 && unlocks==1);
 assert(a6_identity_fields==(valid ? (1U<<(len/4))-1 : 0));
 for(int i=0;i<6;i++) assert(a6_identity_words[i]==(valid && i<len/4 ? wire[i] : 0));
 }
 int errors[]={-ETIMEDOUT,-EPIPE,-ENODEV};
 for(int i=0;i<3;i++){reset();response=errors[i];a6_trial_get_identity(&dev);assert(a6_identity_result==errors[i] && a6_identity_fields==0 && unlocks==1);}
 reset();locked=0;a6_trial_get_identity(&dev);assert(a6_identity_result==-EBUSY && a6_identity_submitted==0 && unlocks==0);
 reset();alloc_fail=1;a6_trial_get_identity(&dev);assert(a6_identity_result==-ENOMEM && a6_identity_submitted==0 && unlocks==1);
 for(int fault=0;fault<6;fault++) {
 reset(); struct usb_device bad=dev;struct config config=cfg;struct alt setting=alt;struct interface interface=iface;
 bad.actconfig=&config;interface.cur_altsetting=&setting;config.interface[0]=&interface;
 if(fault==0) bad.state=6;
 if(fault==1) bad.descriptor.idVendor=1;
 if(fault==2) bad.descriptor.idProduct=1;
 if(fault==3) bad.actconfig=NULL;
 if(fault==4) config.desc.bNumInterfaces=0;
 if(fault==5) setting.desc.bInterfaceNumber=1;
 a6_trial_get_identity(&bad);assert(a6_identity_result==-EPROTO && a6_identity_submitted==0 && unlocks==1);
 }
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    (p/'test.c').write_text(harness+function+main)
    subprocess.run(['cc','-std=c99','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
spec=importlib.util.spec_from_file_location('collector',root/'scripts/a6-capture-wifi-ehci-enum.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base='A6_WIFI_EHCI_ENUM_V2 attempted=1 result=0 restore=0 stage=4 vid=0a5c reset72=09 reset72_after=09 reset_readback=0 gate_before=00000200 gate_after=00000200 phy8=0 phy8_after=0 usb_ctl=c0000080 usb_ctl_after=c0000080 pmu_submitted=2 pmu_completed=2 pmu_restore_submitted=1 pmu_restore_completed=1\n'
id='A6_WIFI_USB_IDENTITY_V1 enabled=1 result=0 length=24 submitted=1 fields=3f request=05 type=c1 value=0001 index=0000 chip=00004334 chiprev=00000002 ramsize=00080000 remapbase=0 boardtype=00001234 boardrev=00000010'
assert m.classify_identity(base+id)=='bootrom_identity_read'
assert m.classify_identity(base+id.replace('length=24','length=8').replace('fields=3f','fields=03'))=='bootrom_identity_read'
assert m.classify_identity(base+id.replace('result=0','result=-110'))=='identity_query_failed_restored'
assert m.classify_identity(base.replace('restore=0','restore=-5')+id)=='restoration_failed'
for old,new in [('fields=3f','fields=03'),('value=0001','value=0000'),('length=24','length=7'),('chip=00004334','chip=00000000')]:
 assert m.classify_identity(base+id.replace(old,new))=='identity_response_invalid_restored'
try: m.classify_identity(base)
except RuntimeError: pass
else: raise AssertionError('missing identity accepted')
print('GETVER wire request, bounded replies/refusals and identity/restoration classifications passed')

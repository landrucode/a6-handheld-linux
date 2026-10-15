#!/usr/bin/env python3
"""Run the actual bounded stock OTP read with mocked USB and clock faults."""
import ast
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT/'scripts/test-a6-wifi-usb-identity.py').read_text())
harness = next(ast.literal_eval(n.value) for n in tree.body
               if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'harness' for t in n.targets))
harness = harness[:harness.index('static int usb_control_msg')]
harness += r'''
typedef uint32_t u32;
static unsigned long jiffies;
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
#define min_t(t,a,b) ((t)(a)<(t)(b) ? (t)(a) : (t)(b))
#define jiffies_to_msecs(x) (x)
#define msecs_to_jiffies(x) (x)
static int a6_otp_result;
static unsigned a6_otp_submitted, a6_otp_completed, a6_otp_bytes;
static u32 a6_otp_start, a6_otp_end;
static unsigned char a6_otp_data[512];
static unsigned first=64,last=576,calls,fail_at,advance=1;
static unsigned addresses[258];
static int usb_control_msg(struct usb_device *d,unsigned pipe,int req,int type,int value,int index,void *buffer,int size,int ms) {
 assert(pipe==0x80 && req==17 && type==0xc1 && size==16 && ms>0 && ms<=250);
 unsigned addr=(unsigned)value | (unsigned)index<<16;
 assert(calls<258);addresses[calls++]=addr;
 if(calls==1) assert(addr==0x1800083a);
 else if(calls==2) assert(addr==0x18000838);
 else assert(addr==0x18000800+first+2*(calls-3) && addr<0x18000800+last);
 jiffies+=advance;
 if(fail_at==calls) return response;
 uint32_t *reply=buffer;
 reply[3]=calls==1 ? last<<3 : calls==2 ? first<<3 : 0x12340000 | calls;
 return 16;
}
'''
s=(ROOT/'kernel/platform/ehci-a6-trial.c').read_text()
a=s.index('static int a6_trial_otp_word(')
b=s.index('\n#endif',a)
functions=s[a:b]
main=r'''
static void reset(void) {
 a6_identity_result=0;a6_identity_fields=63;
 a6_identity_words[0]=0x4334;a6_identity_words[1]=3;
 a6_identity_words[2]=0x80000;a6_identity_words[3]=0x60000000;
 a6_otp_submitted=a6_otp_completed=a6_otp_bytes=calls=jiffies=unlocks=alloc_fail=fail_at=0;
 a6_otp_result=-EAGAIN;a6_otp_start=a6_otp_end=0;
 first=64;last=576;advance=1;response=-EPIPE;locked=1;
 memset(a6_otp_data,0,sizeof(a6_otp_data));
}
int main(void) {
 struct alt alt={.desc={0}};struct interface iface={&alt};
 struct config cfg={.desc={1},.interface={&iface}};
 struct usb_device dev={.state=7,.descriptor={0x0a5c,0xbd1a},.actconfig=&cfg};
 for(unsigned len=2;len<=512;len+=2) {
 reset();last=first+len;a6_trial_get_otp(&dev);
 assert(a6_otp_result==0 && a6_otp_bytes==len && calls==len/2+2 && unlocks==1);
 assert(a6_otp_completed==calls && a6_otp_submitted==calls);
 for(unsigned i=0;i<len;i+=2) {
  unsigned word=i/2+3;assert(a6_otp_data[i]==(word&255) && a6_otp_data[i+1]==(word>>8));
 }
 }
 unsigned ranges[][2]={{64,64},{66,64},{63,65},{64,65},{64,578},{8190,8191}};
 for(unsigned i=0;i<sizeof(ranges)/sizeof(ranges[0]);i++) {
 reset();first=ranges[i][0];last=ranges[i][1];a6_trial_get_otp(&dev);
 assert(a6_otp_result==-ERANGE && calls==2 && a6_otp_bytes==0 && unlocks==1);
 }
 int errors[]={0,4,15,17,-EPIPE,-ETIMEDOUT,-ENODEV};
 for(unsigned i=0;i<sizeof(errors)/sizeof(errors[0]);i++) for(unsigned f=1;f<=258;f++) {
 reset();fail_at=f;response=errors[i];a6_trial_get_otp(&dev);
 assert(a6_otp_result==(response<0 ? response : -EMSGSIZE));
 assert(calls==f && a6_otp_submitted==f && a6_otp_completed==f-1 && a6_otp_bytes==0 && unlocks==1);
 for(unsigned j=0;j<512;j++) assert(a6_otp_data[j]==0);
 }
 reset();advance=250;a6_trial_get_otp(&dev);
 assert(a6_otp_result==-ETIMEDOUT && jiffies==10000 && calls==40 && a6_otp_bytes==0 && unlocks==1);
 for(int fault=0;fault<6;fault++) {
 reset();if(fault==0)a6_identity_result=-EPIPE;
 if(fault==1)a6_identity_fields=3;
 if(fault==2)a6_identity_words[0]++;
 if(fault==3)a6_identity_words[1]++;
 if(fault==4)a6_identity_words[2]++;
 if(fault==5)a6_identity_words[3]++;
 a6_trial_get_otp(&dev);assert(a6_otp_result==-EPROTO && calls==0 && unlocks==0);
 }
 reset();locked=0;a6_trial_get_otp(&dev);assert(a6_otp_result==-EBUSY && calls==0 && unlocks==0);
 reset();alloc_fail=1;a6_trial_get_otp(&dev);assert(a6_otp_result==-ENOMEM && calls==0 && unlocks==1);
 reset();alt.desc.bInterfaceNumber=1;a6_trial_get_otp(&dev);assert(a6_otp_result==-EPROTO && calls==0 && unlocks==1);
 reset();iface.cur_altsetting=NULL;a6_trial_get_otp(&dev);assert(a6_otp_result==-EPROTO && calls==0 && unlocks==1);
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    (p/'test.c').write_text(harness+functions+main)
    subprocess.run(['cc','-fsanitize=address,undefined','-fno-omit-frame-pointer',
                    '-o',str(p/'test'),str(p/'test.c')],check=True)
    subprocess.run([str(p/'test')],check=True)
print('Stock OTP IN request, all valid lengths, range/refusal/error/deadline guards passed')

import importlib.util
spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base='A6_WIFI_EHCI_ENUM_V2 attempted=1 result=0 restore=0 stage=4 vid=0a5c reset72=09 reset72_after=09 reset_readback=0 gate_before=00000200 gate_after=00000200 phy8=0 phy8_after=0 usb_ctl=c0000080 usb_ctl_after=c0000080 pmu_submitted=2 pmu_completed=2 pmu_restore_submitted=1 pmu_restore_completed=1\n'
identity='A6_WIFI_USB_IDENTITY_V1 enabled=1 result=0 length=24 submitted=1 fields=3f request=05 type=c1 value=0001 index=0000 chip=00004334 chiprev=00000003 ramsize=00080000 remapbase=60000000 boardtype=00000000 boardrev=00000000\n'
otp='A6_WIFI_USB_OTP_V1 enabled=1 result=0 submitted=4 completed=4 bytes=4 start=64 end=68 request=11 type=c1 reply_bytes=16 data_word=3 data=03000400'
assert m.classify_otp(base+identity+otp)=='bootrom_otp_read'
assert m.classify_otp(base.replace('restore=0','restore=-5')+identity+otp)=='restoration_failed'
assert m.classify_otp(base+identity.replace('chiprev=00000003','chiprev=00000002')+otp)=='otp_identity_mismatch_restored'
assert m.classify_otp(base+identity+otp.replace('result=0','result=-110'))=='otp_query_failed_restored'
for old,new in [('completed=4','completed=3'),('submitted=4','submitted=5'),('bytes=4','bytes=3'),('start=64','start=63'),('end=68','end=70'),('request=11','request=12'),('data=03000400','data=0300'),('reply_bytes=16','reply_bytes=12')]:
    assert m.classify_otp(base+identity+otp.replace(old,new))=='otp_response_invalid_restored'
print('OTP collector requires exact identity, complete bounded data and restoration')

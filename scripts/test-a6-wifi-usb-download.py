#!/usr/bin/env python3
"""Execute the actual ROM-only downloader with USB, file and clock fault injection."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'kernel/platform/a6-wifi-usb-download.inc').read_text()
a=s.index('static unsigned int a6_download_timeout(')
b=s.index('\n#endif',a)
functions=s[a:b]
harness=r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t u32;
typedef uint32_t __le32;
typedef unsigned char u8;
#define GFP_KERNEL 0
#define USB_STATE_CONFIGURED 7
#define USB_DIR_IN 128
#define USB_TYPE_VENDOR 64
#define USB_RECIP_INTERFACE 1
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,y) ((x)=(y))
#define pr_info(...) ((void)0)
#define le32_to_cpu(x) (x)
#define le16_to_cpu(x) (x)
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
#define msecs_to_jiffies(x) (x)
#define jiffies_to_msecs(x) (x)
#define A6_WIFI_FW_BYTES 456108
#define A6_WIFI_FW_CRC32 0x12345678U
struct endpoint {struct {unsigned bEndpointAddress; bool bulkout;} desc;};
struct usb_host_interface {struct {int bInterfaceNumber,bNumEndpoints;} desc;struct endpoint endpoint[2];};
struct interface {struct usb_host_interface *cur_altsetting;};
struct config {struct {int bNumInterfaces;} desc;struct interface *interface[1];};
struct usb_device {int state;struct {int idVendor,idProduct;} descriptor;struct config *actconfig;int dev;};
struct firmware {size_t size;const u8 *data;};
static struct firmware image;
static unsigned long jiffies;
static int a6_identity_result, a6_otp_result, a6_trial_phase;
static unsigned a6_identity_fields,a6_otp_bytes;
static u32 a6_identity_words[6];
static u8 a6_otp_data[512];
static int a6_download_result;
static u32 a6_download_state,a6_download_rom_bytes;
static unsigned a6_download_submitted,a6_download_completed,a6_download_control_submitted,a6_download_control_completed;
static unsigned a6_download_sent,a6_download_expected,a6_download_endpoint;
static unsigned bulk_calls,control_calls,offset,fail_bulk,fail_control,advance,alloc_calls,alloc_fail;
static int control_reply,bulk_error,short_bulk,fw_error,locked,unlocks,releases,crc_valid,waiting,pending;
static unsigned usb_rcvctrlpipe(struct usb_device*d,int n){assert(n==0);return 128;}
static unsigned usb_sndbulkpipe(struct usb_device*d,int n){assert(n==2);return 2;}
static bool usb_endpoint_is_bulk_out(const void *desc){return ((const struct endpoint*)desc)->desc.bulkout;}
static unsigned get_unaligned_le32(const void *p){unsigned x;memcpy(&x,p,4);return x;}
static unsigned crc32_le(unsigned seed,const void *data,size_t len){assert(seed==~0U && len==image.size-12);return crc_valid?A6_WIFI_FW_CRC32:0;}
static int request_firmware_direct(const struct firmware **fw,const char *name,void *dev){assert(strcmp(name,"a6-centennial-tdk.trx")==0);*fw=&image;return fw_error;}
static void release_firmware(const struct firmware *fw){assert(fw==&image);releases++;}
static int usb_trylock_device(struct usb_device*d){return locked;}
static void usb_unlock_device(struct usb_device*d){unlocks++;}
static void *kmalloc(size_t n,int f){return ++alloc_calls==alloc_fail ? NULL : malloc(n);}
static void *kzalloc(size_t n,int f){void*p=kmalloc(n,f);if(p)memset(p,0,n);return p;}
#define kfree free
static void msleep(unsigned n){jiffies+=n;}
static int usb_control_msg(struct usb_device*d,unsigned pipe,int req,int type,int value,int index,void *buf,int n,int timeout){
 assert(pipe==128 && req==0 && type==0xc1 && value==1 && index==0 && n==8 && timeout>0 && timeout<=1000);
 control_calls++;jiffies+=advance;
 if(control_calls==fail_control)return control_reply;
 __le32*r=buf;r[0]=control_calls==1 ? (waiting ? 1:0) : control_calls==2 || pending ? 1:4;r[1]=offset;
 return 8;
}
static int usb_bulk_msg(struct usb_device*d,unsigned pipe,void *buf,int n,int *actual,int timeout){
 assert(pipe==2 && n>0 && n<=1500 && timeout>0 && timeout<=1000);
 assert(memcmp(buf,image.data+offset,n)==0 && buf!=image.data+offset);
 bulk_calls++;jiffies+=advance;
 if(bulk_calls==fail_bulk){*actual=short_bulk?n-1:0;offset+=*actual;return bulk_error;}
 *actual=n;offset+=n;return 0;
}
'''
main=r'''
static void reset(void){
 jiffies=bulk_calls=control_calls=offset=fail_bulk=fail_control=alloc_calls=alloc_fail=unlocks=releases=0;
 a6_download_submitted=a6_download_completed=a6_download_control_submitted=a6_download_control_completed=0;
 a6_download_sent=a6_download_expected=a6_download_endpoint=0;a6_download_state=~0U;a6_download_rom_bytes=0;
 advance=1;locked=crc_valid=1;fw_error=short_bulk=waiting=pending=0;control_reply=-EPIPE;bulk_error=-EPIPE;
 a6_identity_result=a6_otp_result=0;a6_identity_fields=63;a6_otp_bytes=250;
 a6_identity_words[0]=0x4334;a6_identity_words[1]=3;a6_identity_words[2]=0x80000;a6_identity_words[3]=0x60000000;
 const u8 prefix[]={0x15,0x1b,8,0,'s','=','B','3',0,'M','=','H','E','I','N',' ','m','=','2','.','6',' ','V','=','t',0,0,0,255};
 memcpy(a6_otp_data,prefix,sizeof(prefix));
}
int main(void){
 u8*bytes=calloc(1,A6_WIFI_FW_BYTES);assert(bytes);image.size=A6_WIFI_FW_BYTES;image.data=bytes;
 unsigned header[]={0x30524448,A6_WIFI_FW_BYTES,A6_WIFI_FW_CRC32,0x10020,0x6ee28,0x81,A6_WIFI_FW_BYTES-28-0x6ee28};memcpy(bytes,header,sizeof(header));
 struct usb_host_interface alt={.desc={0,1},.endpoint={{{2,true}}}};
 struct interface iface={&alt};struct config cfg={.desc={1},.interface={&iface}};
 struct usb_device dev={.state=7,.descriptor={0x0a5c,0xbd1a},.actconfig=&cfg};
 reset();a6_trial_download(&dev);assert(a6_download_result==0 && bulk_calls==305 && control_calls==3 && a6_download_sent==A6_WIFI_FW_BYTES && a6_download_state==4 && unlocks==1 && releases==1);
 for(unsigned f=1;f<=305;f++)for(int shortcase=0;shortcase<2;shortcase++){
 reset();fail_bulk=f;short_bulk=shortcase;bulk_error=shortcase?0:-EPIPE;a6_trial_download(&dev);
 assert(a6_download_result==(shortcase?-EIO:-EPIPE) && bulk_calls==f && a6_download_completed==f-1 && unlocks==1 && releases==1);
 }
 for(unsigned f=1;f<=3;f++)for(int len=-1;len<=10;len++){
 if(len==8)continue;reset();fail_control=f;control_reply=len<0?-ETIMEDOUT:len;a6_trial_download(&dev);
 assert(a6_download_result==(len<0?-ETIMEDOUT:-EMSGSIZE) && control_calls==f && unlocks==1 && releases==1);
 }
 reset();advance=1000;a6_trial_download(&dev);assert(a6_download_result==-ETIMEDOUT && jiffies==30000 && releases==1 && unlocks==1);
 reset();pending=1;a6_trial_download(&dev);assert(a6_download_result==-ETIMEDOUT && control_calls==12);
 reset();waiting=1;a6_trial_download(&dev);assert(a6_download_result==-EPROTO && bulk_calls==0 && control_calls==1);
 for(unsigned i=0;i<7;i++){reset();((unsigned*)bytes)[i]^=1;a6_trial_download(&dev);assert(a6_download_result==-EBADMSG && bulk_calls==0 && control_calls==0 && unlocks==0 && releases==1);((unsigned*)bytes)[i]^=1;}
 reset();crc_valid=0;a6_trial_download(&dev);assert(a6_download_result==-EBADMSG && bulk_calls==0 && unlocks==0);
 reset();a6_otp_data[3]^=1;a6_trial_download(&dev);assert(a6_download_result==-EPROTO && bulk_calls==0 && releases==0);
 reset();locked=0;a6_trial_download(&dev);assert(a6_download_result==-EBUSY && bulk_calls==0 && releases==1);
 for(unsigned i=1;i<=2;i++){reset();alloc_fail=i;a6_trial_download(&dev);assert(a6_download_result==-ENOMEM && bulk_calls==0 && unlocks==1 && releases==1);}
 reset();alt.desc.bNumEndpoints=0;a6_trial_download(&dev);assert(a6_download_result==-EPROTO && bulk_calls==0 && unlocks==1 && releases==1);
 free(bytes);
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(harness+functions+main)
    subprocess.run(['cc','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
print('Actual ROM-only download: complete image, every bulk error/short reply, state/deadline/identity/CRC/refusal guards passed')

import importlib.util
spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base='A6_WIFI_EHCI_ENUM_V2 attempted=1 result=0 restore=0 stage=4 vid=0a5c reset72=09 reset72_after=09 reset_readback=0 gate_before=00000200 gate_after=00000200 phy8=0 phy8_after=0 usb_ctl=c0000080 usb_ctl_after=c0000080 pmu_submitted=2 pmu_completed=2 pmu_restore_submitted=1 pmu_restore_completed=1\n'
identity='A6_WIFI_USB_IDENTITY_V1 enabled=1 result=0 length=24 submitted=1 fields=3f request=05 type=c1 value=0001 index=0000 chip=00004334 chiprev=00000003 ramsize=00080000 remapbase=60000000 boardtype=00000000 boardrev=00000000\n'
otp='A6_WIFI_USB_OTP_V1 enabled=1 result=0 submitted=127 completed=127 bytes=250 start=64 end=314 request=11 type=c1 reply_bytes=16 data_word=3 data='+('00'*250)+'\n'
download='A6_WIFI_USB_DOWNLOAD_V1 enabled=1 result=0 bulk_submitted=305 bulk_completed=305 control_submitted=3 control_completed=3 sent=456108 expected=456108 state=4 rom_bytes=456108 endpoint=02 go_submitted=0'
assert m.classify_download(base+identity+otp+download)=='firmware_download_runnable_restored'
assert m.classify_download(base.replace('restore=0','restore=-5')+identity+otp+download)=='restoration_failed'
assert m.classify_download(base+identity+otp+download.replace('result=0','result=-110'))=='firmware_download_failed_restored'
for old,new in [('bulk_completed=305','bulk_completed=304'),('control_completed=3','control_completed=2'),('sent=456108','sent=456107'),('state=4','state=1'),('go_submitted=0','go_submitted=1'),('rom_bytes=456108','rom_bytes=456107'),('endpoint=02','endpoint=00')]:
    assert m.classify_download(base+identity+otp+download.replace(old,new))=='firmware_download_invalid_restored'
print('Download collector requires full ROM bytes/runnable state, zero GO and restoration')

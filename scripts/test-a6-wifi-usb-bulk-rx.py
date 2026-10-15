#!/usr/bin/env python3
"""Execute actual receive/ownership helpers and BCDC decoder under sanitizers."""
from pathlib import Path
import subprocess,tempfile,importlib.util,re,sys,contextlib,io
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'kernel/platform/a6-wifi-usb-bulk-rx.inc').read_text()
decls=s[s.index('static int a6_rx_result'):s.index('\nssize_t a6_ehci_bulk_rx(char *buf)\n{')]
functions=s[s.index('/* No automatic matching'):s.rindex('#endif')]
harness=r'''
#define A6_WIFI_USB_RX 1
#include <sys/types.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
typedef uint32_t u32;
#define GFP_KERNEL 0
#define noinline __attribute__((noinline))
#define USB_STATE_CONFIGURED 7
#define USB_SPEED_HIGH 3
#define le16_to_cpu(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
struct usb_device_id {int unused;};
struct usb_endpoint_descriptor {unsigned bEndpointAddress,bmAttributes,wMaxPacketSize;};
struct usb_host_interface {struct {unsigned bInterfaceNumber,bAlternateSetting,bInterfaceClass,bInterfaceSubClass,bInterfaceProtocol,bNumEndpoints;} desc;struct {struct usb_endpoint_descriptor desc;} endpoint[4];};
struct usb_interface {struct {void *driver;} dev;struct usb_host_interface *cur_altsetting;void *data;};
struct config {struct {unsigned bNumInterfaces;} desc;struct usb_interface *interface[1];};
struct usb_device {unsigned state,speed;struct {unsigned idVendor,idProduct,bNumConfigurations;} descriptor;struct config *actconfig;};
struct usb_driver {const char *name;int(*probe)(struct usb_interface*,const struct usb_device_id*);void(*disconnect)(struct usb_interface*);unsigned no_dynamic_id,soft_unbind,supports_autosuspend;const void *id_table;unsigned driver;};
static int a6_runtime_result,a6_execute_result,a6_trial_phase;
static unsigned a6_runtime_completed,a6_runtime_chip,a6_runtime_chiprev;
static unsigned registered,reg_calls,dereg_calls,locks,lock_available,claim_calls,release_calls,bulk_calls,allocs;
static int reg_fail,claim_fail,alloc_fail,release_fail,usb_result,actual_length;
static struct usb_interface *owned;
static unsigned char packet[2048];
static bool usb_endpoint_xfer_bulk(struct usb_endpoint_descriptor *ep){return (ep->bmAttributes&3)==2;}
static unsigned usb_endpoint_num(struct usb_endpoint_descriptor *ep){return ep->bEndpointAddress&15;}
static bool usb_endpoint_dir_in(struct usb_endpoint_descriptor *ep){return ep->bEndpointAddress&128;}
static void *kzalloc(unsigned n,int flags){allocs++;return alloc_fail?NULL:calloc(1,n);}
#define kfree free
static int usb_trylock_device(struct usb_device *d){if(!lock_available)return 0;assert(!locks);locks=1;return 1;}
static void usb_unlock_device(struct usb_device *d){assert(locks);locks=0;}
static void usb_set_intfdata(struct usb_interface *i,void *p){i->data=p;}
static void *usb_get_intfdata(struct usb_interface *i){return i->data;}
static u32 get_unaligned_le32(const void *p){u32 v;memcpy(&v,p,4);return v;}
static int usb_register_driver(struct usb_driver *drv,void *owner,const char *name){
 assert(!locks&&!registered&&owner==NULL&&!strcmp(name,"a6_wifi_bulk_rx"));
 assert(drv->no_dynamic_id&&!drv->id_table&&!drv->supports_autosuspend&&drv->soft_unbind);
 assert(drv->probe(NULL,NULL)==-ENODEV);reg_calls++;if(reg_fail)return reg_fail;registered=1;return 0;
}
static void usb_deregister(struct usb_driver *drv){assert(!locks&&registered);if(owned){drv->disconnect(owned);owned->dev.driver=NULL;owned=NULL;}registered=0;dereg_calls++;}
static int usb_driver_claim_interface(struct usb_driver *drv,struct usb_interface *i,void *data){assert(locks&&registered&&!i->dev.driver);claim_calls++;if(claim_fail)return claim_fail;i->dev.driver=&drv->driver;i->data=data;owned=i;return 0;}
static void usb_driver_release_interface(struct usb_driver *drv,struct usb_interface *i){assert(locks&&registered&&owned==i);release_calls++;if(release_fail)return;drv->disconnect(i);i->dev.driver=NULL;owned=NULL;}
static unsigned usb_rcvbulkpipe(struct usb_device *d,unsigned ep){assert(ep==1);return 0x81;}
static int usb_bulk_msg(struct usb_device *d,unsigned pipe,void *buf,int n,int *actual,int timeout){
 assert(locks&&registered&&owned&&pipe==0x81&&n==2048&&timeout==2000);bulk_calls++;
 memcpy(buf,packet,2048);*actual=actual_length;return usb_result;
}
'''
main=r'''
static struct usb_host_interface alt;
static struct usb_interface intf;
static struct config cfg;
static struct usb_device dev;
static void init(void){
 a6_rx_result=a6_rx_usb_result=a6_rx_release=-EAGAIN;
 a6_rx_attempted=a6_rx_registered=a6_rx_deregistered=a6_rx_claimed=a6_rx_disconnected=a6_rx_submitted=0;
 a6_rx_wrapper_bytes=0;
 a6_rx_snapshot_bytes=0;memset(a6_rx_snapshot,0,sizeof(a6_rx_snapshot));
 a6_rx_bytes=a6_rx_in=a6_rx_out=a6_rx_mps=a6_rx_frames=a6_rx_payload=a6_rx_type=a6_rx_layout_mask=a6_rx_event_type=a6_rx_event_length=a6_rx_event_version=0;
 a6_runtime_result=a6_execute_result=0;a6_runtime_completed=3;a6_runtime_chip=0x4334;a6_runtime_chiprev=3;
 registered=reg_calls=dereg_calls=locks=claim_calls=release_calls=bulk_calls=allocs=0;lock_available=1;
 reg_fail=claim_fail=alloc_fail=release_fail=0;usb_result=-ETIMEDOUT;actual_length=0;owned=NULL;
 memset(&alt,0,sizeof(alt));alt.desc.bInterfaceClass=255;alt.desc.bInterfaceSubClass=2;alt.desc.bInterfaceProtocol=255;alt.desc.bNumEndpoints=2;
 alt.endpoint[0].desc=(struct usb_endpoint_descriptor){0x81,2,512};alt.endpoint[1].desc=(struct usb_endpoint_descriptor){2,2,512};
 memset(&intf,0,sizeof(intf));intf.cur_altsetting=&alt;cfg.desc.bNumInterfaces=1;cfg.interface[0]=&intf;
 dev=(struct usb_device){7,3,{0xa5c,0xbd1a,1},&cfg};memset(packet,0,sizeof(packet));packet[0]=0x20;packet[16]=0x88;packet[17]=0x6c;
}
static void cleaned(void){assert(!registered&&!locks&&!owned&&!intf.dev.driver&&!intf.data);assert(reg_calls==dereg_calls);}
static void wrap(unsigned n){
 memmove(packet+16,packet,n-16);memset(packet,0,16);
 packet[0]=0x11;packet[1]=0x80;packet[4]=n&255;packet[5]=n>>8;
 unsigned sum=0;for(unsigned i=0;i<16;i+=2)sum+=packet[i]+(packet[i+1]<<8);
 sum=(~(sum+(sum>>16)))&65535;packet[2]=sum&255;packet[3]=sum>>8;
}
int main(int argc,char **argv){
 if(argc==2){
  init();FILE *f=fopen(argv[1],"rb");assert(f);
  actual_length=fread(packet,1,sizeof(packet),f);assert(feof(f));fclose(f);
  usb_result=0;a6_trial_bulk_rx(&dev);cleaned();
  assert(a6_rx_result==0&&a6_rx_bytes==178&&a6_rx_wrapper_bytes==16);
  assert(a6_rx_frames==1&&a6_rx_payload==158&&a6_rx_type==0x886c);
  assert(a6_rx_layout_mask==2&&a6_rx_event_type==52&&a6_rx_event_version==2&&a6_rx_event_length==84);
  assert(a6_rx_snapshot_bytes==178&&!memcmp(a6_rx_snapshot,packet,178));
  puts("PASS private hardware packet replay: wrapper16, BCDC2, Ethernet158, TRACE52/version2/body84 and complete cleanup");return 0;
 }
 for(unsigned n=34;n<=2048;n++){
  init();wrap(n);usb_result=0;actual_length=n;a6_trial_bulk_rx(&dev);cleaned();
  assert(a6_rx_result==0&&a6_rx_wrapper_bytes==16&&a6_rx_payload==n-20);
 }
 for(unsigned byte=0;byte<16;byte++){
  init();wrap(178);packet[byte]^=1;usb_result=0;actual_length=178;
  a6_trial_bulk_rx(&dev);cleaned();assert(a6_rx_result<0&&!a6_rx_frames&&!a6_rx_wrapper_bytes);
 }
 for(unsigned kind=1;kind<8;kind++){
  init();wrap(178);packet[1]|=kind<<4;usb_result=0;actual_length=178;
  a6_trial_bulk_rx(&dev);cleaned();assert(a6_rx_result==-EPROTO&&!a6_rx_frames);
 }
 for(unsigned n=2;n<34;n++){
  init();wrap(34);usb_result=0;actual_length=n;a6_trial_bulk_rx(&dev);cleaned();assert(a6_rx_result<0&&!a6_rx_frames);
 }

 char saved[2048];
 init();assert(a6_ehci_bulk_rx_data(saved,-1,1)==-EINVAL);
 assert(a6_ehci_bulk_rx_data(saved,0,2048)==0);
 init();usb_result=0;actual_length=178;a6_trial_bulk_rx(&dev);
 assert(a6_rx_snapshot_bytes==178);
 memset(saved,0,sizeof(saved));assert(a6_ehci_bulk_rx_data(saved,0,sizeof(saved))==178);
 assert(!memcmp(saved,packet,178));
 for(int off=0;off<=2049;off++) {
   ssize_t n=a6_ehci_bulk_rx_data(saved,off,sizeof(saved));
   assert(n==(off<178?178-off:0));
   if(n)assert(!memcmp(saved,packet+off,n));
 }
 assert(a6_ehci_bulk_rx_data(saved,0,0)==0);
 init();usb_result=-ETIMEDOUT;actual_length=178;a6_trial_bulk_rx(&dev);
 assert(!a6_rx_snapshot_bytes&&a6_ehci_bulk_rx_data(saved,0,2048)==0);

 init();a6_trial_bulk_rx(&dev);cleaned();assert(a6_rx_result==-ETIMEDOUT&&a6_rx_usb_result==-ETIMEDOUT&&bulk_calls==1&&a6_rx_claimed==1&&a6_rx_disconnected==1&&a6_rx_release==0&&!a6_rx_frames);
 a6_trial_bulk_rx(&dev);assert(a6_rx_result==-EPERM&&bulk_calls==1&&reg_calls==1);
 init();usb_result=0;actual_length=18;a6_trial_bulk_rx(&dev);cleaned();assert(a6_rx_result==0&&a6_rx_frames==1&&a6_rx_payload==14&&a6_rx_type==0x886c);
 for(int fail=0;fail<5;fail++){init();switch(fail){case 0:reg_fail=-ENOMEM;break;case 1:lock_available=0;break;case 2:alloc_fail=1;break;case 3:claim_fail=-EBUSY;break;case 4:release_fail=1;break;}a6_trial_bulk_rx(&dev);assert(a6_rx_result<0&&!registered&&!locks&&!owned);if(fail!=4)assert(!bulk_calls);else assert(a6_rx_release==-EUCLEAN&&bulk_calls==1);}
 for(int guard=0;guard<20;guard++){init();switch(guard){
 case 0:a6_runtime_result=-5;break;case 1:a6_execute_result=-5;break;case 2:a6_runtime_completed=2;break;case 3:a6_runtime_chip=4334;break;
 case 4:dev.state=0;break;case 5:dev.speed=1;break;case 6:dev.descriptor.idProduct=1;break;case 7:dev.descriptor.bNumConfigurations=2;break;
 case 8:dev.actconfig=NULL;break;case 9:cfg.desc.bNumInterfaces=2;break;case 10:cfg.interface[0]=NULL;break;case 11:intf.cur_altsetting=NULL;break;
 case 12:intf.dev.driver=(void*)1;break;case 13:alt.desc.bInterfaceNumber=1;break;case 14:alt.desc.bAlternateSetting=1;break;
 case 15:alt.desc.bInterfaceClass=0;break;case 16:alt.desc.bInterfaceSubClass=0;break;case 17:alt.desc.bInterfaceProtocol=0;break;
 case 18:alt.desc.bNumEndpoints=1;break;case 19:alt.desc.bNumEndpoints=5;break;}
 a6_trial_bulk_rx(&dev);assert(a6_rx_result<0&&!bulk_calls&&!registered&&!locks);}
 for(unsigned endpoint=0;endpoint<2;endpoint++)for(int problem=0;problem<6;problem++){init();struct usb_endpoint_descriptor *e=&alt.endpoint[endpoint].desc;
 switch(problem){case 0:e->bEndpointAddress=0;break;case 1:e->bEndpointAddress|=0x10;break;case 2:e->wMaxPacketSize=64;break;
 case 3:e->bmAttributes=3;break;case 4:e->bEndpointAddress=endpoint?0x82:1;break;case 5:alt.desc.bNumEndpoints=3;alt.endpoint[2].desc=*e;break;}
 a6_trial_bulk_rx(&dev);assert(a6_rx_result<0&&!bulk_calls);cleaned();}
 for(int error=-32;error<0;error++){init();usb_result=error;a6_trial_bulk_rx(&dev);assert(a6_rx_result==error&&!a6_rx_frames);cleaned();}
 for(int n=-1;n<=2049;n++){init();usb_result=0;actual_length=n;a6_trial_bulk_rx(&dev);cleaned();assert((n>=18&&n<=2048)?a6_rx_result==0:a6_rx_result<0);}
 for(unsigned offset=0;offset<256;offset++)for(unsigned n=4;n<1040;n+=7){init();packet[3]=offset;
 int rc=a6_rx_decode(packet,n);assert((4+offset*4+14<=n)?rc==0:rc==-EMSGSIZE);}
 for(unsigned flags=0;flags<256;flags++){init();packet[0]=flags;assert((flags>>4)==2?a6_rx_decode(packet,18)==0:a6_rx_decode(packet,18)==-EPROTO);}
 for(unsigned reversed=0;reversed<2;reversed++)for(unsigned prefix=0;prefix<5;prefix++){
  init();unsigned off=prefix*4, n=off+178;memset(packet,0,sizeof(packet));
  packet[off]=0x11;packet[off+12]=0x88;packet[off+13]=0x6c;packet[off+14]=0x80;packet[off+15]=1;
  packet[off+20]=0x10;packet[off+21]=0x18;packet[off+23]=1;packet[off+25]=2;packet[off+31]=54;packet[off+47]=106;
  if(reversed)for(unsigned w=0;w+3<n;w+=4){unsigned char t=packet[w];packet[w]=packet[w+3];packet[w+3]=t;t=packet[w+1];packet[w+1]=packet[w+2];packet[w+2]=t;}
  usb_result=0;actual_length=n;a6_trial_bulk_rx(&dev);cleaned();
  assert(a6_rx_result==-EPROTO&&a6_rx_frames==0&&a6_rx_layout_mask==(1U<<(reversed*5+prefix))&&a6_rx_event_type==54&&a6_rx_event_version==2&&a6_rx_event_length==106);
  a6_rx_layout_mask=0;a6_rx_inspect(packet,off+71);assert(!a6_rx_layout_mask);
  a6_rx_inspect(packet,off+177);assert(!a6_rx_layout_mask); /* declared body truncated */
  for(unsigned bad=0;bad<6;bad++){
   unsigned fields[]={12,14,20,23,25,47};unsigned pos=(off+fields[bad])^(reversed?3:0);
   unsigned char saved=packet[pos];packet[pos]=bad==4?3:saved+1;
   a6_rx_layout_mask=0;a6_rx_inspect(packet,n);assert(!a6_rx_layout_mask);packet[pos]=saved;
  }
  packet[(off+25)^(reversed?3:0)]=1;a6_rx_layout_mask=0;a6_rx_inspect(packet,n);assert(a6_rx_layout_mask==(1U<<(reversed*5+prefix))&&a6_rx_event_version==1);
  a6_rx_layout_mask=0;a6_rx_inspect(NULL,0);a6_rx_inspect(NULL,2049);assert(!a6_rx_layout_mask);
 }
 for(unsigned iface=1;iface<16;iface++){init();packet[2]=iface;assert(a6_rx_decode(packet,18)==-EPROTO);}
 return 0;
}
'''
replay = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else None
if replay and not replay.is_relative_to(ROOT/'build'):
 raise ValueError('hardware packet replay must remain private under build/')
with tempfile.TemporaryDirectory(dir=ROOT/'build' if replay else None) as td:
 p=Path(td);(p/'test.c').write_text(harness+decls+functions+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')]+([str(replay)] if replay else []),check=True)
assert 'header=%' not in (ROOT/'kernel/platform/a6-wifi-usb-bulk-rx.inc').read_text()
print('PASS layout signature/version/bounds and absence of raw header export; actual receive helpers: device/endpoint/ownership guards, register/claim/release cleanup, one IN/no OUT, USB errors/lengths and exhaustive BCDC bounds')
sp=importlib.util.spec_from_file_location('capture',ROOT/'scripts/a6-capture-wifi-ehci-enum.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
other=(ROOT/'scripts/test-a6-wifi-usb-runtime.py').read_text();a=other.index("base='A6_WIFI_EHCI_ENUM");b=other.index('assert m.classify_runtime',a)
# This is the shared independent synthetic status fixture, never private data.
exec(other[a:b],globals())
prefix+=status
rx='A6_WIFI_USB_BULK_RX_V1 enabled=1 result=0 attempted=1 usb_result=0 registered=1 deregistered=1 claimed=1 disconnected=1 release=0 submitted=1 bytes=18 in=81 out=02 mps=512 frames=1 payload=14 type=886c header=00000020 tx=0\n'
assert m.classify_bulk_rx(prefix+rx)=='bulk_rx_frame_observed_restored'
quiet=rx.replace('result=0','result=-110').replace('bytes=18','bytes=0').replace('frames=1','frames=0').replace('payload=14','payload=0')
assert m.classify_bulk_rx(prefix+quiet)=='bulk_rx_quiet_timeout_restored'
for old,new in [('deregistered=1','deregistered=0'),('release=0','release=-5'),('disconnected=1','disconnected=0')]:assert m.classify_bulk_rx(prefix+rx.replace(old,new))=='bulk_rx_driver_release_unverified'
for old,new in [('tx=0','tx=1'),('submitted=1','submitted=2')]:assert m.classify_bulk_rx(prefix+rx.replace(old,new))=='bulk_rx_failed_restored'
for old,new in [('bytes=18','bytes=4096'),('frames=1','frames=0'),('in=81','in=01'),('payload=14','payload=19')]:assert m.classify_bulk_rx(prefix+rx.replace(old,new))=='bulk_rx_invalid_restored'
assert m.classify_bulk_rx(prefix+quiet.replace('bytes=0','bytes=1'))=='bulk_rx_failed_restored'
print('PASS collector distinguishes valid frame, quiet timeout, transfer failure and driver-release failure without overclaiming data transport')
pre=('auto=1 paused=0 fault=0 attached=1\nA6_LOW_BATTERY_CANDIDATE_V3 enabled=1 attended_trial=0 attended_plugged=0 threshold_mv=3600\n'
     'A6_WIFI_EHCI_ENUM_V2 attempted=0 \nA6_EHCI_PROGRESS_V1 phase=0 \n'
     'A6_WIFI_USB_IDENTITY_V1 enabled=1 \nA6_WIFI_USB_OTP_V1 enabled=1 \n'
     'A6_WIFI_USB_DOWNLOAD_V1 enabled=1 \nA6_WIFI_USB_EXECUTE_V1 enabled=1 \n'
     'A6_WIFI_USB_RUNTIME_V1 enabled=1 \nA6_WIFI_USB_BULK_RX_V1 enabled=1 \n')
commands=[]
def serial(command,timeout=20):commands.append(command);return subprocess.CompletedProcess([],0,pre,'')
m.serial=serial;original=sys.argv
try:
 sys.argv=['collector','--runtime']
 try:
  with contextlib.redirect_stdout(io.StringIO()):m.main()
 except RuntimeError as e:assert str(e)=='Bulk-receive image requires explicit --rx; no trial submitted'
 else:raise AssertionError('implicit receive accepted')
 assert len(commands)==1 and '/run;' not in commands[0] and '/run ' not in commands[0]
 assert len((commands[0]+"; printf '%s%s\\n' A6_ENUM_END_000 0000000000000\n").encode())<1024
finally:sys.argv=original
print('PASS actual preflight refuses implicit receive before one-shot and fits shell line bound')

#!/usr/bin/env python3
"""Exercise the generated upstream RX callback and stock-derived TX builder."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('patch',ROOT/'scripts/prepare-a6-brcmfmac-hsic-patch.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
s=m.render((ROOT/'.deps/linux'/m.USB).read_text())
start=s.index('static void brcmf_usb_rx_complete(struct urb *urb)\n{')
stop=s.index('\nstatic void',start+1)
callback=s[start:stop]
harness=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
typedef uint8_t u8;typedef uint16_t u16;
#define le16_to_cpu(x) (x)
#define BRCMFMAC_USB_STATE_UP 1
#define BRCMFMAC_USB_STATE_SLEEP 2
#define brcmf_dbg(...) ((void)0)
struct sk_buff {u8 bytes[2048];u8 *data;unsigned len;};
struct usb_device {int dev;struct {unsigned idVendor,idProduct;}descriptor;};
struct brcmf_usbdev_info {struct usb_device *usbdev;int dev,rx_freeq;struct {int state;}bus_pub;};
struct brcmf_usbreq {struct brcmf_usbdev_info *devinfo;struct sk_buff *skb;};
struct urb {struct brcmf_usbreq *context;int status,actual_length;struct usb_device *dev;};
static unsigned frees,refills,frames,marked,enqueued,deleted,frame_length;
static int opted;
static unsigned device_property_read_bool(void *p,const char *name){assert(!strcmp(name,"apple,hsic-usb-header"));return opted;}
static void brcmf_usb_del_fromq(struct brcmf_usbdev_info *d,struct brcmf_usbreq *r){deleted++;}
static void brcmu_pkt_buf_free_skb(struct sk_buff *s){frees++;}
static void brcmf_usb_enq(struct brcmf_usbdev_info *d,int *q,struct brcmf_usbreq *r,void *unused){enqueued++;}
static void skb_put(struct sk_buff *s,unsigned n){assert(s->len+n<=sizeof(s->bytes));s->len+=n;}
static void skb_pull(struct sk_buff *s,unsigned n){assert(n<=s->len);s->data+=n;s->len-=n;}
static void brcmf_rx_frame(int d,struct sk_buff *s,int handle_event,int reorder){assert(handle_event&&reorder);frames++;frame_length=s->len;}
static void brcmf_usb_rx_refill(struct brcmf_usbdev_info *d,struct brcmf_usbreq *r){refills++;}
static void usb_mark_last_busy(struct usb_device *d){marked++;}
'''
main=r'''
static struct sk_buff skb;
static struct usb_device usb;
static struct brcmf_usbdev_info dev;
static struct brcmf_usbreq req;
static struct urb urb;
static void init(unsigned n){
 memset(&skb,0,sizeof(skb));skb.data=skb.bytes;
 usb=(struct usb_device){0,{0xa5c,0xbd1a}};
 dev=(struct brcmf_usbdev_info){&usb,0,0,{BRCMFMAC_USB_STATE_UP}};
 req=(struct brcmf_usbreq){&dev,&skb};urb=(struct urb){&req,0,n,&usb};
 frees=refills=frames=marked=enqueued=deleted=frame_length=0;opted=1;
}
static void rx_header(unsigned n){
 assert(!brcmf_a6_hsic_tx_header(skb.bytes,n-16,1));
 skb.bytes[1]=0x80;skb.bytes[2]=skb.bytes[3]=0;
 unsigned sum=0;for(unsigned i=0;i<16;i+=2)sum+=skb.bytes[i]+(skb.bytes[i+1]<<8);
 sum=~((sum&65535)+(sum>>16));skb.bytes[2]=sum&255;skb.bytes[3]=(sum>>8)&255;
 skb.bytes[16]=0x20;
}
int main(int argc,char **argv){
 if(argc==2){
  init(178);FILE *f=fopen(argv[1],"rb");assert(f);
  assert(fread(skb.bytes,1,sizeof(skb.bytes),f)==178);fclose(f);
  brcmf_usb_rx_complete(&urb);
  assert(frames==1&&frame_length==162&&skb.data==skb.bytes+16&&!frees);
  assert(refills==1&&marked==1&&deleted==1&&!req.skb);
  puts("PASS private hardware capture through generated upstream callback: stripped16, handed162 to brcmfmac, refill1/free0");return 0;
 }
 for(unsigned n=17;n<=2048;n++){
  init(n);rx_header(n);brcmf_usb_rx_complete(&urb);
  assert(frames==1&&frame_length==n-16&&skb.data==skb.bytes+16&&!frees&&refills==1&&marked==1&&!req.skb);
 }
 for(unsigned byte=0;byte<16;byte++){
  init(178);rx_header(178);skb.bytes[byte]^=1;brcmf_usb_rx_complete(&urb);
  assert(frees==1&&!frames&&refills==1&&marked==1&&deleted==1&&!req.skb);
 }
 for(unsigned kind=1;kind<8;kind++){
  init(178);rx_header(178);skb.bytes[1]|=kind<<4;brcmf_usb_rx_complete(&urb);
  assert(frees==1&&!frames&&refills==1);
 }
 init(178);rx_header(178);opted=0;brcmf_usb_rx_complete(&urb);assert(frames==1&&frame_length==178&&skb.data==skb.bytes);
 init(18);skb.bytes[0]=0x20;brcmf_usb_rx_complete(&urb);assert(frames==1&&frame_length==18&&skb.data==skb.bytes);
 init(178);rx_header(178);usb.descriptor.idProduct=1;brcmf_usb_rx_complete(&urb);assert(frees==1&&!frames&&refills==1);
 init(178);rx_header(178);urb.status=-ETIMEDOUT;brcmf_usb_rx_complete(&urb);assert(frees==1&&!frames&&!refills&&enqueued==1);
 init(178);rx_header(178);dev.bus_pub.state=0;brcmf_usb_rx_complete(&urb);assert(frees==1&&!frames&&!refills&&enqueued==1);
 u8 header[16];
 for(unsigned payload=1;payload<=65519;payload++)for(unsigned seq=0;seq<65536;seq+=8191){
  assert(!brcmf_a6_hsic_tx_header(header,payload,seq));
  assert(header[0]==1&&header[1]==0xa0&&brcmf_a6_hsic_word(header+4)==payload+16&&brcmf_a6_hsic_word(header+6)==seq);
  unsigned sum=0;for(unsigned i=0;i<16;i+=2)sum+=header[i]+(header[i+1]<<8);
  while(sum>>16)sum=(sum&65535)+(sum>>16);assert(sum==65535);
  for(unsigned i=8;i<16;i++)assert(header[i]==0);
  assert(brcmf_a6_hsic_rx_offset(header,payload+16)==-EPROTO); /* TX kind cannot be accepted as RX */
 }
 memset(header,0x5a,16);assert(brcmf_a6_hsic_tx_header(header,0,1)==-EMSGSIZE);
 assert(brcmf_a6_hsic_tx_header(header,65520,1)==-EMSGSIZE);for(unsigned i=0;i<16;i++)assert(header[i]==0x5a);
 puts("PASS upstream RX callback cleanup/refill/drop/opt-in/device guards and exhaustive TX lengths/sequence/checksum/direction");return 0;
}
'''
replay=Path(sys.argv[1]).resolve() if len(sys.argv)==2 else None
if replay and not replay.is_relative_to(ROOT/'build'):raise ValueError('private replay must stay under build/')
with tempfile.TemporaryDirectory(dir=ROOT/'build' if replay else None) as td:
 p=Path(td);(p/'test.c').write_text(harness+(ROOT/'kernel/platform/brcmfmac-a6-hsic.h').read_text()+callback+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')]+([str(replay)] if replay else []),check=True)

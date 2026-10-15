#!/usr/bin/env python3
"""Compile actual offline scan codec and verify ABI offsets against pinned C."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
fw=(ROOT/'.deps/linux/drivers/net/wireless/broadcom/brcm80211/brcmfmac/fwil_types.h').read_text()
bss=fw[fw.index('struct brcmf_bss_info_le {'):];bss=bss[:bss.index('\n};')+3]
pre=r'''
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t u8;typedef int8_t s8;typedef uint16_t __le16;typedef uint32_t __le32;
#define ETH_ALEN 6
#define BRCMF_MCSSET_LEN 16
'''
main=r'''
_Static_assert(sizeof(struct brcmf_bss_info_le)==128,"BSS109 size");
_Static_assert(offsetof(struct brcmf_bss_info_le,SSID_len)==18,"SSID offset");
_Static_assert(offsetof(struct brcmf_bss_info_le,rateset)==52,"rates offset");
_Static_assert(offsetof(struct brcmf_bss_info_le,ie_offset)==116,"IE offset");
_Static_assert(offsetof(struct brcmf_bss_info_le,ie_length)==120,"IE length");
static void fixture(unsigned char*p){memset(p,0,2048);a6_scan_put(p,144,4);a6_scan_put(p+4,109,4);a6_scan_put(p+8,0x1234,2);a6_scan_put(p+10,1,2);a6_scan_put(p+12,109,4);a6_scan_put(p+16,132,4);a6_scan_put(p+128,128,2);a6_scan_put(p+132,4,4);p[140]=0;p[141]=2;p[142]='a';p[143]='b';}
int main(void){unsigned char p[2048],save[2048];unsigned short c[]={0x2b01,0x2b06,0x2b0b};
 assert(a6_scan_request(p,sizeof(p),c,3,0x1234,0)==80);
 assert(a6_scan_le(p,4)==1&&a6_scan_le(p+4,2)==1&&a6_scan_le(p+6,2)==0x1234);
 for(unsigned i=8;i<44;i++)assert(!p[i]);for(unsigned i=44;i<50;i++)assert(p[i]==255);
 assert(p[50]==2&&p[51]==1&&!a6_scan_le(p+52,4)&&a6_scan_le(p+60,4)==120&&a6_scan_le(p+68,4)==3);
 for(unsigned i=0;i<3;i++)assert(a6_scan_le(p+72+i*2,2)==c[i]);assert(!p[78]&&!p[79]);
 for(unsigned n=0;n<80;n++)assert(a6_scan_request(p,n,c,3,0x1234,0)==-EMSGSIZE);
 assert(a6_scan_request(p,sizeof(p),NULL,0,0x1234,0)==-EINVAL);
 assert(a6_scan_request(p,sizeof(p),c,14,0x1234,0)==-EINVAL);
 assert(a6_scan_request(p,sizeof(p),c,3,0,0)==-EINVAL);
 assert(a6_scan_request(p,sizeof(p),NULL,0,0x1234,1)==72&&a6_scan_le(p+4,2)==3);
 fixture(p);assert(a6_scan_partial(p,144,0x1234)==1);memcpy(save,p,sizeof(p));
 for(unsigned n=0;n<144;n++)assert(a6_scan_partial(p,n,0x1234)<0);
 assert(a6_scan_partial(p,144,1)==-ESTALE);
 unsigned pos[]={0,4,10,12,16,30,64,128,132,141};unsigned val[]={255,2,2,108,128,33,17,127,255,3};
 for(unsigned i=0;i<sizeof(pos)/sizeof(pos[0]);i++){memcpy(p,save,sizeof(p));p[pos[i]]=val[i];assert(a6_scan_partial(p,144,0x1234)<0);}
 memcpy(p,save,sizeof(p));a6_scan_put(p+132,~0U,4);assert(a6_scan_partial(p,144,0x1234)==-EMSGSIZE);
 /* Every suffix byte count for an IE stream: odd dangling header refused. */
 for(unsigned n=0;n<=64;n++){fixture(p);a6_scan_put(p,140+n,4);a6_scan_put(p+16,128+n,4);a6_scan_put(p+132,n,4);memset(p+140,0,n);assert(a6_scan_partial(p,140+n,0x1234)==(n%2?-EMSGSIZE:1));}
 assert(a6_scan_partial(NULL,0,0x1234)==-EMSGSIZE);
 puts("PASS actual C escan v1 passive request/abort, explicit channel/dwell bounds, pinned BSS109 offsets, sync/version/length/count/SSID/rate/IE bounds and truncation");}
'''
with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
 p=Path(td);(p/'test.c').write_text(pre+bss+'\n'+(ROOT/'kernel/platform/a6-wifi-scan-codec.h').read_text()+main)
 subprocess.run(['cc','-fsanitize=address,undefined','-g','-O1',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)

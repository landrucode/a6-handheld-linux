#!/usr/bin/env python3
"""Compile actual event inspection in both profiles; optional private replay."""
from pathlib import Path
import subprocess, tempfile, sys
ROOT = Path(__file__).resolve().parents[1]
s = (ROOT / 'kernel/platform/a6-wifi-usb-bulk-rx.inc').read_text()
helpers = s[s.index('static unsigned int a6_rx_layout_byte'):s.index('/* Ordinary receive')]
pre = r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define noinline __attribute__((noinline))
static u32 a6_rx_layout_mask,a6_rx_event_type,a6_rx_event_length;
static unsigned a6_rx_event_version,a6_rx_wrapper_bytes;
'''
main = r'''
static void clear(void){a6_rx_layout_mask=a6_rx_event_type=a6_rx_event_length=a6_rx_event_version=0;}
int main(int argc,char **argv){
 unsigned char p[2048];
 for(unsigned rev=0;rev<2;rev++)for(unsigned prefix=0;prefix<5;prefix++){
  unsigned off=prefix*4,n=off+156;memset(p,0,sizeof(p));
  p[off+12]=0x88;p[off+13]=0x6c;p[off+14]=0x80;p[off+15]=1;
  p[off+20]=0x10;p[off+21]=0x18;p[off+23]=1;p[off+25]=2;p[off+31]=52;p[off+47]=84;
  if(rev)for(unsigned i=0;i<sizeof(p);i+=4){unsigned char t=p[i];p[i]=p[i+3];p[i+3]=t;t=p[i+1];p[i+1]=p[i+2];p[i+2]=t;}
#ifdef A6_WIFI_USB_LOOPBACK
  unsigned expected=(!rev&&prefix==1)?2:0;
#else
  unsigned expected=1U<<(rev*5+prefix);
#endif
  clear();a6_rx_inspect(p,n);assert(a6_rx_layout_mask==expected);
  if(expected){assert(a6_rx_event_type==52&&a6_rx_event_version==2&&a6_rx_event_length==84);
   p[(off+31)^(rev?3:0)]=54;a6_rx_inspect(p,n);assert(a6_rx_event_type==52);p[(off+31)^(rev?3:0)]=52;
  }
  for(unsigned len=0;len<n;len++){clear();a6_rx_inspect(p,len);assert(!a6_rx_layout_mask);}
  unsigned fields[]={12,14,20,23,25,47};
  for(unsigned k=0;k<6;k++){unsigned pos=(off+fields[k])^(rev?3:0);unsigned char save=p[pos];p[pos]=k==4?3:save+1;clear();a6_rx_inspect(p,n);assert(!a6_rx_layout_mask);p[pos]=save;}
  p[(off+25)^(rev?3:0)]=1;clear();a6_rx_inspect(p,n);assert(a6_rx_layout_mask==expected);if(expected)assert(a6_rx_event_version==1);
 }
 clear();a6_rx_inspect(NULL,0);a6_rx_inspect(NULL,2049);assert(!a6_rx_layout_mask);
 for(int i=1;i<argc;i++){
  FILE *f=fopen(argv[i],"rb");assert(f);unsigned n=fread(p,1,sizeof(p),f);assert(feof(f));fclose(f);
  const unsigned char *frame=p;assert(!a6_rx_unwrap_kind(&frame,&n,0x2000));
  clear();a6_rx_inspect(frame,n);assert(a6_rx_layout_mask==2&&a6_rx_event_type==52&&a6_rx_event_version==2&&a6_rx_event_length==84);
 }
 return 0;
}
'''
fixtures = [Path(x).resolve() for x in sys.argv[1:]]
assert all(p.is_relative_to(ROOT/'build') for p in fixtures), 'Replay stays private under build/'
with tempfile.TemporaryDirectory(dir=ROOT/'build') as td:
 p=Path(td);(p/'test.c').write_text(pre+helpers+main)
 for loopback in (False, True):
  subprocess.run(['cc','-fsanitize=address,undefined','-g']+(['-DA6_WIFI_USB_LOOPBACK=1'] if loopback else [])+[str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')]+[str(f) for f in fixtures],check=True)
print('PASS actual C canonical/legacy inspection: prefixes, byte order, versions, signature/body bounds and first-event metadata')
print('Private TRACE fixtures replayed: '+str(len(fixtures)))

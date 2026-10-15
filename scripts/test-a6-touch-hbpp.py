#!/usr/bin/env python3
"""Exercise actual 16-byte HBPP handler with inherited power/CS fault cases."""
from pathlib import Path
import runpy, subprocess, tempfile
repo = Path(__file__).resolve().parents[1]
old = runpy.run_path(str(repo/'scripts/test-a6-touch-gpio-cs.py'))
p = old['p']
needle = 'return received==1 ? (fault==1 ? 0xff : 0xd0) : 0;'
assert needle in p
p = p.replace('static int fault;', 'static int fault;\nstatic unsigned hbpp_words[2]={0x1f01,0x1f01};')
p = p.replace(needle, '''if(fault==1)return 0xff;
  if(received<=4){unsigned w=hbpp_words[(received-1)/2];
   return received%2 ? w>>8 : w&255;}
  return 0;''')
# Validate the literal request, FIFO counts, and no extra TX in every case.
p = p.replace('   spiwords++;', '''   static const unsigned tx[]={0x1a,0xa1,0x18,0xe1,0x18,0xe1,0x18,0xe1,
    0x18,0xe1,0x18,0xe1,0x18,0xe1,0x18,0xe1};
   assert(spiwords<16 && value==tx[spiwords]);
   assert(*(u32*)(spi+0x34)==16 && *(u32*)(spi+0x4c)==16);
   spiwords++;''')
source = '#define A6_TOUCH_HBPP 1\n'+old['source']
tests = old['tests'].replace('"check-with-gpio-cs",18','"check-hbpp",10').replace(')==18)',')==10)')
tests = tests.replace('a6_check_rx[0]==0xd0','a6_check_rx[0]==0x1f')
tests = tests.replace('spiwords<=4','spiwords<=16').replace('f==3 ? 4 : 0','f==3 ? 16 : 0')
tests = tests.replace(' puts("PASS GPIO-CS', '''
 const unsigned accepted[]={0x18e1,0x1aa1,0x1f01,0x4879,0x4969,0x4ad1,0x4bc1};
 for(unsigned a=0;a<7;a++)for(unsigned b=0;b<7;b++){
  init(0,0);hbpp_words[0]=accepted[a];hbpp_words[1]=accepted[b];
  assert(a6_check_run_store(NULL,NULL,"check-hbpp",10)==10);
  assert(a6_check_received==16 && fifo_reads==16 && spiwords==16 && a6_check_restored);
 }
 const unsigned bad[]={0,0xffff,0xd000,0x011f,0x4878,0x4ad0,0x4bc0};
 for(unsigned a=0;a<7;a++)for(unsigned which=0;which<2;which++){
  init(0,0);hbpp_words[0]=hbpp_words[1]=0x1f01;hbpp_words[which]=bad[a];
  assert(a6_check_run_store(NULL,NULL,"check-hbpp",10)==-EPROTO);
  assert(a6_check_received==16 && a6_check_restored && a6_power_restored);
 }
 puts("PASS HBPP exact packet, all accepted pairs, invalid words, bounds; GPIO-CS''')
with tempfile.TemporaryDirectory(prefix='a6-hbpp-test-') as tmp:
 c=Path(tmp)/'test.c';c.write_text(p+source+old['old']['setup']+tests);exe=Path(tmp)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

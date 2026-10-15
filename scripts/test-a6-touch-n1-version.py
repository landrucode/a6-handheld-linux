#!/usr/bin/env python3
"""Compile and exercise the bounded N1 controller-version read."""
from pathlib import Path
import runpy, subprocess, tempfile
repo = Path(__file__).resolve().parents[1]
old = runpy.run_path(str(repo/'scripts/test-a6-touch-hbpp.py'))
p = old['p']
p = p.replace('static unsigned hbpp_words[2]={0x1f01,0x1f01};',
              'static unsigned char version_rx[8]={0,0,0xa0,0x11,0x4d,0x43,0,0};')
start = p.index('  if(received<=4){unsigned w=hbpp_words')
end = p.index('  return 0;', start) + len('  return 0;')
p = p[:start] + '  if(received<=8)return version_rx[received-1];\n  return 0;' + p[end:]
p = p.replace('0x1a,0xa1,0x18,0xe1,0x18,0xe1,0x18,0xe1,\n    0x18,0xe1,0x18,0xe1,0x18,0xe1,0x18,0xe1',
              '0x1c,0x73,0x8f,0xfc,0x10,0x00,0x01,0x9b')
p = p.replace('spiwords<16 && value==tx[spiwords]', 'spiwords<8 && value==tx[spiwords]')
p = p.replace('*(u32*)(spi+0x34)==16 && *(u32*)(spi+0x4c)==16',
              '*(u32*)(spi+0x34)==8 && *(u32*)(spi+0x4c)==8')
source = old['source'].replace('#define A6_TOUCH_HBPP 1', '#define A6_TOUCH_N1_VERSION 1')
setup = old['old']['old']['setup'] + old['tests'].split('int main(void){',1)[0]
tests = r'''
int main(void){
 init(0,0);
 int rr=a6_check_run_store(NULL,NULL,"read-n1-version",15);
 assert(rr==15);
 assert(a6_check_received==8 && spiwords==8 && a6_check_restored);
 assert(a6_n1_version_value==0x434d11a0 && a6_check_result==0);
 init(0,0); version_rx[2]=0;
 assert(a6_check_run_store(NULL,NULL,"read-n1-version",15)==-EPROTO);
 assert(a6_check_received==8 && a6_check_restored);
 init(0,0); privileged=false;
 assert(a6_check_run_store(NULL,NULL,"read-n1-version",15)==-EPERM && !writes);
 init(0,0); version_rx[2]=0xa0;
 assert(a6_check_run_store(NULL,NULL,"read-n1-version",15)==15);
 assert(a6_check_run_store(NULL,NULL,"read-n1-version",15)==-EALREADY);
 puts("PASS N1 version request, checksum/address bytes, expected packed version, mismatch, privilege and one-shot");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-n1-version-test-') as tmp:
 c=Path(tmp)/'test.c'; c.write_text(p+source+setup+tests); exe=Path(tmp)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

#!/usr/bin/env python3
"""Exercise the real PWM+CHECK handlers with fault injection and no hardware."""
import ast
from pathlib import Path
import subprocess
import tempfile
repo=Path(__file__).resolve().parents[1]
ast_tree=ast.parse((repo/'scripts/test-a6-touch-check.py').read_text())
preamble=next(ast.literal_eval(n.value) for n in ast_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='preamble' for t in n.targets))
preamble=preamble.replace('static unsigned writes,', '''static unsigned char pwm[4096];
static void *a6_touch_pwm=pwm;
static u32 a6_memory_capture_copy[704];
#define A6_TOUCH_PWM_GATE 0x124
static unsigned pwm_writes;
static unsigned writes,''')
preamble=preamble.replace('static u32 readl(void *p) {', '''static u32 readl(void *p) {
 if(fault==8 && p==pwm+0x10 && delays>=10 && *(u32*)p) return 365;
''')
preamble=preamble.replace(' writes++;', ''' writes++;
 if (p>= (void*)pwm && p < (void*)(pwm+4096)) {
  pwm_writes++;
  assert(p==pwm+0x10 || p==pwm+0x14 || p==pwm+0x20);
  if(p==pwm+0x20 && v==0)assert(*(u32*)(gpio+A6_TOUCH_RESET)==0x202);
  if(p==pwm+0x20 && v==0x4003) { *(u32*)p=fault==9 ? 0x4003 : fault==10 ? 0x4000 : fault==11 ? 0x4005 : 0x4001; return; }
  if(fault==6 && p==pwm+0x14 && v) return;
  if(fault==7 && p==pwm+0x20 && !v) return;
 }
 if(p==gpio+A6_TOUCH_RESET && v==0x203) {
  assert(*(u32*)(pwm+0x10)==366 && *(u32*)(pwm+0x14)==366);
  assert(*(u32*)(pwm+0x20)==0x4001);
 }''')
# Use integer comparisons for unrelated mock arrays; pointer ordering is not portable C.
preamble=preamble.replace('p>= (void*)pwm && p < (void*)(pwm+4096)', '(uintptr_t)p >= (uintptr_t)pwm && (uintptr_t)p < (uintptr_t)(pwm+4096)')
source='\n'.join(line for name in ('a6-touch-pwm-check.inc','a6-touch-check.inc') for line in (repo/'kernel/platform'/name).read_text().splitlines() if not line.startswith('#include'))
tests=r'''
static void setup(int f) {
 memset(pmgr,0,sizeof(pmgr)); memset(gpio,0,sizeof(gpio)); memset(spi,0,sizeof(spi)); memset(pwm,0,sizeof(pwm));
 memset(a6_memory_capture_copy,0,sizeof(a6_memory_capture_copy));
 u32 *c=a6_memory_capture_copy;
 c[0]=0x41364d31;c[1]=1;c[5]=19;c[25]=5;c[26]=1;c[27]=1;c[28]=384;
 c[480]=3;c[481]=1;c[482]=4;c[483]=24000000;c[485]=1;
 *(u32*)(pmgr+A6_TOUCH_GATE)=0x2ff;*(u32*)(pmgr+A6_TOUCH_PWM_GATE)=0x2ff;
 *(u32*)(gpio+A6_TOUCH_CS)=0x202;*(u32*)(gpio+A6_TOUCH_RESET)=0x202;
 *(u32*)(spi+4)=8;*(u32*)(spi+12)=3;*(u32*)(spi+48)=1;
 privileged=true;running=false;fault=f;
 writes=pwm_writes=fifo_reads=polls=delays=received=queued=0;
 a6_check_attempted=a6_check_restored=false;a6_check_received=0;
 a6_pwm_probe_written=a6_pwm_probe_readback=a6_pwm_probe_restored=false;
 memset(a6_check_rx,0,4);
}
int main(void) {
 unsigned char original_spi[4096],original_gpio[4096],zeros[4096]={0};
 int expected[]={14,-EPROTO,-ETIMEDOUT,-EIO,-EIO,-EUCLEAN,-EIO,-EUCLEAN,-EIO,-EIO,-EIO,-EIO};
 for(int f=0;f<12;f++) {
  setup(f);memcpy(original_spi,spi,4096);memcpy(original_gpio,gpio,4096);
  assert(a6_check_run_store(NULL,NULL,"check-with-pwm",14)==expected[f]);
  assert(a6_check_attempted && fifo_reads<=4 && polls<=10002);
  assert(a6_pwm_probe_written && a6_pwm_probe_readback==(f!=6 && f!=8 && f<9));
  assert(a6_pwm_probe_restored==(f!=7));
  assert(a6_check_restored==(f!=5 && f!=7));
  assert(a6_pwm_probe_first[0]==366 && a6_pwm_probe_first[1]==(f==6 ? 0 : 366));
  assert(a6_pwm_probe_first[2]==(f==9 ? 0x4003 : f==10 ? 0x4000 : f==11 ? 0x4005 : 0x4001));
  assert(a6_pwm_probe_later[0]==(f==8 ? 365 : 366));
  assert(a6_pwm_probe_later[1]==(f==6 ? 0 : 366));
  assert(a6_pwm_probe_later[2]==(f==9 ? 0x4003 : f==10 ? 0x4000 : f==11 ? 0x4005 : 0x4001));
  if(f==6 || f==8 || f>=9)assert(!fifo_reads && !queued && !a6_check_received);
  assert(pwm_writes==6 && delays<=121020 && !running);
  assert((memcmp(original_spi,spi,4096)!=0)==(f==5));
  assert(!memcmp(original_gpio,gpio,4096));
  assert((memcmp(zeros,pwm,4096)!=0)==(f==7));
  unsigned before=writes;
  assert(a6_check_run_store(NULL,NULL,"check-with-pwm",14)==-EALREADY && writes==before);
 }
 setup(0);privileged=false;
 assert(a6_check_run_store(NULL,NULL,"check-with-pwm",14)==-EPERM && !writes);
 setup(0);assert(a6_check_run_store(NULL,NULL,"check-bootloader",16)==-EINVAL && !writes);
 for(int n=0;n<18;n++) {
  setup(0);u32 *c=a6_memory_capture_copy;
  switch(n) {
   case 0:c[0]=0;break;case 1:c[1]=2;break;case 2:c[5]=20;break;case 3:c[7]=1;break;
   case 4:c[25]=4;break;case 5:c[26]=5;break;case 6:c[27]=2;break;case 7:c[28]=383;break;
   case 8:c[29]=1;break;case 9:c[480]=1;break;case 10:c[481]=2;break;case 11:c[482]=5;break;
   case 12:c[483]=0;break;case 13:c[483]=48000000;break;case 14:c[484]=1;break;case 15:c[485]=2;break;
   case 16:*(u32*)(pmgr+A6_TOUCH_PWM_GATE)=0x200;break;
   case 17:*(u32*)(pwm+0x20)=0x4003;break;
  }
  assert(a6_check_run_store(NULL,NULL,"check-with-pwm",14)<0 && !writes && !a6_check_attempted);
 }
 setup(0);a6_memory_capture_copy[482]=8;
 assert(a6_check_run_store(NULL,NULL,"check-with-pwm",14)==14);
 puts("PASS actual PWM+CHECK: ordering, bounded transfer, all cleanup paths, readback failures, source/state/privilege guards, one-shot");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-pwm-test-') as tmp:
 p=Path(tmp);(p/'test.c').write_text(preamble+source+tests)
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)

#!/usr/bin/env python3
"""Fault-inject the actual fixed PWM gate handler, without phone access."""
import ast
from pathlib import Path
import subprocess
import tempfile
repo=Path(__file__).resolve().parents[1]
module=ast.parse((repo/'scripts/test-a6-touch-check.py').read_text())
preamble=next(ast.literal_eval(n.value) for n in module.body
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='preamble' for t in n.targets))
preamble=preamble.replace(' writes++;', ''' writes++;
 if (p==pmgr+0x124) { *(u32*)p=fault ? v : v|0xf0; return; }''')
preamble += r'''
#define __iomem
#define ioremap(a,b) ((void*)1)
#define iounmap(a) ((void)0)
#define readl_poll_timeout(addr,val,cond,delay,limit) ({ \
 int result=-ETIMEDOUT; \
 for(int i=0;i<10000;i++) { val=readl(addr); if(cond) {result=0;break;} } \
 result; })
'''
source=(repo/'kernel/platform/a6-touch-clock.inc').read_text()
tests=r'''
static void setup(u32 gate) {
 memset(pmgr,0,sizeof(pmgr)); memset(spi,0,sizeof(spi)); memset(gpio,0,sizeof(gpio));
 *(u32*)(pmgr+0x124)=gate; a6_touch_pwm=spi;
 writes=0; privileged=true; fault=0; a6_pwm_attempted=false;
}
int main(void) {
 setup(0x200);
 assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==15);
 assert(writes==1 && a6_pwm_before==0x200 && a6_pwm_after==0x2ff && !a6_pwm_result);
 assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==-EALREADY && writes==1);
 setup(0x2ff);
 assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==15 && !writes);
 setup(0x200); fault=1;
 assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==-ETIMEDOUT);
 assert(writes==1 && a6_pwm_attempted && a6_pwm_result==-ETIMEDOUT);
 assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==-EALREADY && writes==1);
 for(int i=0;i<2;i++) {
  setup(i ? U32_MAX : 0x20f);
  assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==-EBUSY && !writes);
 }
 setup(0x200); privileged=false;
 assert(a6_pwm_enable_store(NULL,NULL,"enable-pwm-gate",15)==-EPERM && !writes);
 setup(0x200);
 assert(a6_pwm_enable_store(NULL,NULL,"invalid",7)==-EINVAL && !writes);
 puts("PASS PWM gate handler: acknowledged/already-on, timeout, one-shot, invalid state/command and privilege guards");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-pwm-test-') as tmp:
    c=Path(tmp)/'test.c';c.write_text(preamble+source+tests)
    exe=Path(tmp)/'test'
    subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)

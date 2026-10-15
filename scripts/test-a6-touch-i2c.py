#!/usr/bin/env python3
"""Fault-inject the actual fixed I2C gate handler, without phone access."""
import ast
from pathlib import Path
import subprocess
import tempfile
repo=Path(__file__).resolve().parents[1]
module=ast.parse((repo/'scripts/test-a6-touch-check.py').read_text())
preamble=next(ast.literal_eval(n.value) for n in module.body
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='preamble' for t in n.targets))
preamble=preamble.replace('#define sysfs_emit(...) 0', '#define sysfs_emit(buf, ...) snprintf(buf,4096,__VA_ARGS__)').replace('#define sysfs_emit_at(...) 0', '#define sysfs_emit_at(buf,n,...) snprintf(buf+n,4096-n,__VA_ARGS__)')
preamble=preamble.replace('static unsigned writes,', 'static unsigned bus_reads, gate_reads;\nstatic unsigned writes,')
preamble=preamble.replace('static u32 readl(void *p) {', """static u32 readl(void *p) {
 if(p==pmgr+0x118) { gate_reads++; if(fault==2 && gate_reads==2)return 0x200; }
 if((uintptr_t)p >= (uintptr_t)spi && (uintptr_t)p < (uintptr_t)(spi+4096)) {
  assert(p==spi+0x14 || p==spi+0x1c || p==spi+0x28); bus_reads++;
 }
""")
preamble=preamble.replace(' writes++;', ''' writes++;
 assert(p==pmgr+0x118);
 if (p==pmgr+0x118) { *(u32*)p=fault ? v : v|0xf0; return; }''')
preamble += r'''
#define __iomem
#define ioremap(a,b) ((void*)1)
#define iounmap(a) ((void)0)
#define readl_poll_timeout(addr,val,cond,delay,limit) ({ \
 int result=-ETIMEDOUT; \
 for(int i=0;i<10000;i++) { val=readl(addr); if(cond) {result=0;break;} } \
 result; })
'''
source=(repo/'kernel/platform/a6-touch-i2c.inc').read_text()
tests=r'''
static void setup(u32 gate) {
 memset(pmgr,0,sizeof(pmgr)); memset(spi,0,sizeof(spi)); memset(gpio,0,sizeof(gpio));
 *(u32*)(pmgr+0x118)=gate; a6_touch_i2c=spi;
 writes=bus_reads=gate_reads=0; privileged=true; fault=0; a6_i2c_attempted=false;
}
int main(void) {
 char buf[4096];
 setup(0x200); assert(a6_i2c_status_show(NULL,NULL,buf)>0 && !bus_reads && !writes);
 setup(0x2ff); assert(a6_i2c_status_show(NULL,NULL,buf)>0 && bus_reads==3 && !writes);
 assert(strstr(buf,"i2c_14=") && strstr(buf,"sda_gpio58="));
 setup(0x2ff); fault=2;
 assert(a6_i2c_status_show(NULL,NULL,buf)>0 && !bus_reads && !writes);
 setup(U32_MAX); assert(a6_i2c_status_show(NULL,NULL,buf)>0 && !bus_reads && !writes);
 setup(0x2ff); privileged=false;
 assert(a6_i2c_status_show(NULL,NULL,buf)==-EPERM && !gate_reads && !bus_reads && !writes);
 setup(0x2ff); fault=2;
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==-EBUSY && !writes);

 setup(0x200);
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==15);
 assert(writes==1 && a6_i2c_before==0x200 && a6_i2c_after==0x2ff && !a6_i2c_result);
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==-EALREADY && writes==1);
 setup(0x2ff);
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==15 && !writes);
 setup(0x200); fault=1;
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==-ETIMEDOUT);
 assert(writes==1 && a6_i2c_attempted && a6_i2c_result==-ETIMEDOUT);
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==-EALREADY && writes==1);
 for(int i=0;i<2;i++) {
  setup(i ? U32_MAX : 0x20f);
  assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==-EBUSY && !writes);
 }
 setup(0x200); privileged=false;
 assert(a6_i2c_enable_store(NULL,NULL,"enable-i2c-gate",15)==-EPERM && !writes);
 setup(0x200);
 assert(a6_i2c_enable_store(NULL,NULL,"invalid",7)==-EINVAL && !writes);
 puts("PASS I2C gate handler: acknowledged/already-on, timeout, one-shot, invalid state/command and privilege guards");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-i2c-test-') as tmp:
    c=Path(tmp)/'test.c';c.write_text(preamble+source+tests)
    exe=Path(tmp)/'test'
    subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)

#!/usr/bin/env python3
"""Run the actual fixed PMU-read handler against a bounded fake controller."""
import ast,subprocess,tempfile
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
m=ast.parse((repo/'scripts/test-a6-touch-check.py').read_text())
p=next(ast.literal_eval(n.value) for n in m.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='preamble' for t in n.targets))
p=p[:p.index('static unsigned writes,')]
p+=r'''
#define A6_TOUCH_I2C_GATE 0x118
static void *a6_touch_i2c=spi;
static unsigned writes,txwords,rxreads,delays,phase,transactions;
static int fault, fail_at;
static bool active, cleaned;
static const u8 regs[]={0x1e,0,0x22,0x23,0x1e};
static void udelay(unsigned n){delays+=n;}
static u32 readl(void *v){
 if(v==spi+0x14 && active) {
  if(transactions==fail_at) {
   if(fault==1)return 0x10010000; /* busy timeout */
   if(fault==2)return 0x08210000; /* NACK */
   if(fault==3)return U32_MAX;
   if(fault==4)return 0x08410000; /* arbitration loss */
   if(fault==5)return 0x09010000; /* jam */
  }
  return 0x08090000; /* XEN, TX empty, RX byte present */
 }
 if(v==spi+4) {
  rxreads++;assert(active);active=false;*(u32*)(spi+0x14)=0x08010000;
  if((fault==6 || fault==10) && transactions==fail_at)return 0x100;
  if(fault==7 && transactions==1)return 2;
  if(fault==8 && transactions==5)return 1;
  return transactions==1 || transactions==5 ? (fault==11 ? 1 : 0) : 0x50+transactions;
 }
 if(v==spi+0x1c && fault==9 && transactions)return 0x105;
 if(v==spi+0x14 && fault==10 && cleaned)return 0x10010000;
 return *(u32*)v;
}
static void writel(u32 value,void *v){
 writes++;
 assert(v==spi || v==spi+0x14 || v==spi+0x1c);
 if(v==spi){
  assert(transactions<5 && !cleaned);
  unsigned expected[]={0x1e8,0x200|regs[transactions],0x1e9,0x601};
  assert(value==expected[phase]);txwords++;phase++;
  if(phase==4){phase=0;transactions++;active=true;}
 }else if(v==spi+0x14){
  *(u32*)v &= ~(value & 0x0fe00040); /* W1C event flags */
 }else{
  assert(value==0x704 || value==0x104);
  if(value==0x704){cleaned=true;active=false;*(u32*)(spi+0x14)=0x10000;}
  *(u32*)v=0x104;
 }
}
'''
source='\n'.join(x for x in (repo/'kernel/platform/a6-touch-pmu-read.inc').read_text().splitlines() if not x.startswith('#include'))
tests=r'''
static void setup(int f,int at){
 memset(spi,0,sizeof(spi));memset(pmgr,0,sizeof(pmgr));memset(gpio,0,sizeof(gpio));
 *(u32*)(pmgr+0x118)=0x2ff;*(u32*)(gpio+0xe8)=*(u32*)(gpio+0xec)=0x221;
 *(u32*)(spi+0x14)=0x08010100;*(u32*)(spi+0x1c)=0x104;*(u32*)(spi+0x28)=1;
 writes=txwords=rxreads=delays=phase=transactions=0;fault=f;fail_at=at;active=cleaned=false;
 privileged=true;a6_pmu_attempted=a6_pmu_idle=a6_pmu_config_ok=a6_pmu_bank_ok=false;
 a6_pmu_received=a6_pmu_polls=0;memset(a6_pmu_bytes,0,5);
}
int main(void){
 int expected[]={15,-ETIMEDOUT,-ENXIO,-EIO,-EIO,-EIO,-ENODATA,-EPROTO,-EPROTO,-EUCLEAN,-EUCLEAN,15};
 for(int f=0;f<=11;f++)for(int at=1;at<=5;at++){
  setup(f,at);
  int result=a6_pmu_run_store(NULL,NULL,"read-pmu-common",15);
  assert(result==expected[f]);
  assert(a6_pmu_attempted && txwords<=20 && rxreads<=5 && delays<=500010 && a6_pmu_polls<=50000);
  assert(a6_pmu_idle==(f!=10) && a6_pmu_config_ok==(f!=9));
  if((f>=1 && f<=6) || f==10)assert(txwords==4*at);
  if(f==7)assert(txwords==4);
  if(!f)assert(a6_pmu_received==5 && a6_pmu_bank_ok && txwords==20 && rxreads==5);
  assert(!memcmp(gpio+0xe8,"\x21\x02\0\0\x21\x02\0\0",8));
  unsigned before=writes;
  assert(a6_pmu_run_store(NULL,NULL,"read-pmu-common",15)==-EALREADY && writes==before);
 }
 for(int i=0;i<8;i++){
  setup(0,1);
  switch(i){
   case 0:*(u32*)(pmgr+0x118)=0x200;break;
   case 1:*(u32*)(gpio+0xe8)=0x220;break;
   case 2:*(u32*)(gpio+0xec)=0x220;break;
   case 3:*(u32*)(spi+0x28)=6;break;
   case 4:*(u32*)(spi+0x1c)=0x105;break;
   case 5:*(u32*)(spi+0x18)=1;break;
   case 6:*(u32*)(spi+0x14)=0x10010100;break;
   case 7:*(u32*)(spi+0x14)=U32_MAX;break;
  }
  assert(a6_pmu_run_store(NULL,NULL,"read-pmu-common",15)==-EBUSY && !writes && !rxreads && !a6_pmu_attempted);
 }
 setup(0,1);privileged=false;
 assert(a6_pmu_run_store(NULL,NULL,"read-pmu-common",15)==-EPERM && !writes);
 setup(0,1);assert(a6_pmu_run_store(NULL,NULL,"write-pmu",9)==-EINVAL && !writes);
 puts("PASS actual PMU reads: fixed FIFO sequence, per-byte timeout/NACK/bus/empty faults, bank checks, config failure, guards and one-shot");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-pmu-test-') as tmp:
 c=Path(tmp)/'test.c';c.write_text(p+source+tests);exe=Path(tmp)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

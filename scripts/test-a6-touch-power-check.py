#!/usr/bin/env python3
"""Actual combined power/PWM/SPI handler; deterministic per-transaction faults."""
from pathlib import Path
import runpy,subprocess,tempfile
repo=Path(__file__).resolve().parents[1]
old=runpy.run_path(str(repo/'scripts/test-a6-touch-pwm-check.py'))
p=old['preamble'].replace('static u32 readl(void *p)', 'static u32 base_readl(void *p)').replace('static void writel(u32 v,void *p)', 'static void base_writel(u32 v,void *p)')
# The original declaration has a space after the comma.
p=p.replace('static void writel(u32 v, void *p)', 'static void base_writel(u32 v, void *p)')
assert 'static void base_writel' in p
p+=r'''
#define A6_TOUCH_I2C_GATE 0x118
static unsigned char i2c[4096],pmu[256];
static void *a6_touch_i2c=i2c;
static unsigned ipart,itx,irx,itrans,ipolls,iresets,railwrites,ana_on,ldo_on,spiwords;
static unsigned words[4];
static bool iactive,iwrite;
static int ifault,ifail;
static u32 readl(void *v){
 if((uintptr_t)v<(uintptr_t)i2c || (uintptr_t)v>=(uintptr_t)(i2c+4096))return base_readl(v);
 if(v==i2c+0x14 && iactive){
  ipolls++;
  if(itrans==(unsigned)ifail){
   if(ifault==1 || ifault==11)return 0x10010000;
   if(ifault==2)return 0x08210000;
   if(ifault==3)return U32_MAX;
   if(ifault==4)return 0x08410000;
   if(ifault==5)return 0x09010000;
  }
  return iwrite ? 0x08010000 : 0x08090000;
 }
 if(v==i2c+4){
  assert(iactive && !iwrite);irx++;
  unsigned reg=words[1]&255;
  if(ifault==6 && itrans==(unsigned)ifail)return 0x100;
  if(ifault==7 && itrans==(unsigned)ifail)return pmu[reg]^1;
  return pmu[reg];
 }
 if(v==i2c+0x1c && ifault==8 && itrans)return 0x105;
 if(v==i2c+0x14 && ifault==11 && iresets)return 0x10010000;
 return *(u32*)v;
}
static void writel(u32 value,void *v){
 if((uintptr_t)v<(uintptr_t)i2c || (uintptr_t)v>=(uintptr_t)(i2c+4096)){
  if(v==gpio+A6_TOUCH_RESET && value==0x203)assert(pmu[0x22]==0xef && pmu[0x23]==0xed);
  if(v==spi+0x10)spiwords++;
  base_writel(value,v);return;
 }
 assert(v==i2c || v==i2c+0x14 || v==i2c+0x1c);
 if(v==i2c){
  assert(!iactive);assert(ipart<4);words[ipart++]=value;itx++;
  if(ipart==1)assert(value==0x1e8);
  if(ipart==2){
   iwrite=!(value&0x200);
   unsigned r=value&255;
   assert(r==0 || r==0x1e || r==0x22 || r==0x23 || r==0x68 || r==0x7f);
   if(iwrite)assert(r==0x22 || r==0x23);
  }
  if(ipart==3 && iwrite){
   assert(value>=0x200 && value<=0x2ff);
   unsigned r=words[1];unsigned d=value&255;
   assert(*(u32*)(gpio+A6_TOUCH_RESET)==0x202);
   if(r==0x22){assert(d==0xeb || d==0xef);if(d==0xef){ana_on++;assert(pmu[0x23]==0xad);} }
   if(r==0x23){assert(d==0xad || d==0xed);if(d==0xed){ldo_on++;assert(pmu[0x22]==0xef);} }
   railwrites++;if(!(ifault==10 && itrans+1==(unsigned)ifail))pmu[r]=d; /* May apply even if controller later reports failure. */
   iactive=true;itrans++;ipart=0;
  }else if(ipart==3)assert(value==0x1e9);
  else if(ipart==4){assert(value==0x601);iactive=true;itrans++;ipart=0;}
 }else if(v==i2c+0x14){
  if(iactive && value==(1U<<27))iactive=false;
  *(u32*)v=0x10000;
 }else{
  assert(value==0x704 || value==0x104);
  if(value==0x704){iresets++;iactive=false;*(u32*)(i2c+0x14)=0x10000;}
  *(u32*)v=0x104;
 }
}
'''
source='\n'.join(line for name in ('a6-touch-pwm-check.inc','a6-touch-power-check.inc','a6-touch-check.inc') for line in (repo/'kernel/platform'/name).read_text().splitlines() if not line.startswith('#include'))
setup=old['tests'][:old['tests'].index('int main(void)')]
tests=r'''
static void init(int f,int at){
 setup(0);memset(i2c,0,sizeof(i2c));memset(pmu,0,sizeof(pmu));
 *(u32*)(pmgr+0x118)=0x2ff;*(u32*)(gpio+0xe8)=*(u32*)(gpio+0xec)=0x221;
 *(u32*)(i2c+0x14)=0x08010100;*(u32*)(i2c+0x1c)=0x104;*(u32*)(i2c+0x28)=1;
 pmu[0]=0x34;pmu[0x22]=0xeb;pmu[0x23]=0xad;pmu[0x68]=0x10;pmu[0x7f]=0x12;
 ifault=f;ifail=at;ipart=itx=irx=itrans=ipolls=iresets=railwrites=ana_on=ldo_on=spiwords=0;
 iactive=iwrite=false;
 a6_power_transactions=a6_power_polls=0;
 a6_power_saved=a6_power_maybe_ana=a6_power_maybe_ldo=false;
 a6_power_idle=a6_power_config_ok=a6_power_restored=false;
 a6_power_start_result=a6_power_cleanup_result=0;
 memset(a6_power_before,0,6);memset(a6_power_enabled,0,2);memset(a6_power_after,0,5);
}
int main(void){
 init(0,0);
 assert(a6_check_run_store(NULL,NULL,"check-with-power",16)==16);
 assert(a6_check_restored && a6_power_restored && a6_power_transactions==17);
 assert(railwrites==4 && ana_on==1 && ldo_on==1 && a6_check_rx[0]==0xd0);
 assert(a6_power_before[4]==0x10 && a6_power_after[3]==0x10);
 for(int f=1;f<=7;f++)for(int at=1;at<=17;at++){
  init(f,at);
  int ret=a6_check_run_store(NULL,NULL,"check-with-power",16);
  assert(a6_check_attempted);
  assert(itrans<=24 && itx<=96 && irx<=24 && ipolls<=240000 && iresets<=4);
  assert(ana_on<=1 && ldo_on<=1 && railwrites<=4 && spiwords<=4 && delays<=2600000);
  assert(pmu[0x68]==0x10 && pmu[0x7f]==0x12 && pmu[0x1e]==0);
  if(f<=5 || (f==6 && at!=7 && at!=9 && at!=11 && at!=12))assert(ret<0);
  if(at<=6 && f<=6)assert(!railwrites && !spiwords);
  if(at<=10 && (f<=5 || (f==6 && at!=7 && at!=9)))assert(!spiwords);
  if(a6_power_restored){assert(pmu[0x22]==0xeb && pmu[0x23]==0xad);}
  assert(*(u32*)(gpio+A6_TOUCH_RESET)==0x202);
  unsigned before=itx;
  assert(a6_check_run_store(NULL,NULL,"check-with-power",16)==-EALREADY && itx==before);
 }
 /* Existing SPI/PWM failures still unwind both rails. */
 for(int f=1;f<12;f++){
  init(0,0);fault=f;
  assert(a6_check_run_store(NULL,NULL,"check-with-power",16)<0);
  assert(a6_power_restored && pmu[0x22]==0xeb && pmu[0x23]==0xad);
 }
 for(int k=0;k<8;k++){
  init(0,0);
  switch(k){
   case 0:*(u32*)(pmgr+0x118)=0x200;break;
   case 1:*(u32*)(gpio+0xe8)=0x220;break;
   case 2:*(u32*)(gpio+0xec)=0x220;break;
   case 3:*(u32*)(i2c+0x28)=6;break;
   case 4:*(u32*)(i2c+0x1c)=0x105;break;
   case 5:*(u32*)(i2c+0x18)=1;break;
   case 6:*(u32*)(i2c+0x14)=0x10000;break;
   case 7:a6_touch_i2c=NULL;break;
  }
  assert(a6_check_run_store(NULL,NULL,"check-with-power",16)<0 && !writes && !itx && !a6_check_attempted);
  a6_touch_i2c=i2c;
 }
 init(0,0);pmu[0x1e]=1;
 assert(a6_check_run_store(NULL,NULL,"check-with-power",16)==-EPROTO && itrans==1 && !railwrites);
 init(8,0);assert(a6_check_run_store(NULL,NULL,"check-with-power",16)==-EUCLEAN);
 init(11,7);assert(a6_check_run_store(NULL,NULL,"check-with-power",16)==-EUCLEAN);
 assert(!a6_power_restored && !spiwords && itrans==7);
 for(int at=7;at<=12;at++){
  if(at==8 || at==10)continue;
  init(10,at);assert(a6_check_run_store(NULL,NULL,"check-with-power",16)<0);
  if(at<=9)assert(a6_power_restored && !spiwords);
  else assert(!a6_power_restored);
 }
 init(0,0);privileged=false;
 assert(a6_check_run_store(NULL,NULL,"check-with-power",16)==-EPERM && !itx);
 init(0,0);assert(a6_check_run_store(NULL,NULL,"check-with-pwm",14)==-EINVAL && !itx);
 puts("PASS actual power/PWM/CHECK: per-operation faults, applied-on-error rollback, bank/source/privilege guards, fixed writes, ordering and bounds");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-power-test-') as tmp:
 c=Path(tmp)/'test.c';c.write_text(p+source+setup+tests);exe=Path(tmp)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

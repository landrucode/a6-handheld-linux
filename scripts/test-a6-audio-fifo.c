// SPDX-License-Identifier: GPL-2.0-only
/* Host MMIO fault injection of the actual audio sysfs handler. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <stdarg.h>
#include <sys/types.h>
#define BIT(x) (1U<<(x))
#define max(a,b) ((a)>(b)?(a):(b))
#define min(a,b) ((a)<(b)?(a):(b))
struct file {};
struct bin_attribute {struct {const char *name;int mode;} attr; size_t size; void *read;};
typedef uint32_t u32;
#define __iomem
#define __init
#define U32_MAX UINT32_MAX
#define CAP_SYS_RAWIO 1
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define A6_TOUCH_I2C_GATE 0x118
static uint8_t pmgr[4096], gpio[4096], i2c[4096], mca[4096], nco[4096], acs[4096];
static uint8_t iis2[4096], audio_switch[4096];
static int lock_held, fail_amp_gate, fail_iis_ack, fail_gpio_release, fail_gpio_restore, fail_route, amp_nack, amp_timeout, amp_recover_fail, amp_id_reads;
static unsigned int fifo, serial_writes, fifo_reads, elapsed;
static int fail_nco, fail_reset, no_drain, slow_drain;
#define A6_POWER_XIP BIT(28)
#define A6_POWER_XEN BIT(27)
#define A6_POWER_RX BIT(19)
#define A6_POWER_TX BIT(16)
#define A6_POWER_ERR (BIT(25)|BIT(24)|BIT(23)|BIT(22)|BIT(21)|BIT(6))
static void *a6_touch_pmgr=pmgr,*a6_touch_gpio=gpio,*a6_touch_i2c=i2c;
static int a6_touch_lock, lock_busy, fail_enable=-1, fail_restore=-1, writes, reads_mca;
static void *firmware_kobj;
static u32 a6_memory_capture_copy[704];
struct kobject {};
struct attribute {int dummy;};
struct kobj_attribute {struct attribute attr;};
struct attribute_group {const char *name;struct attribute **attrs;const struct bin_attribute *const *bin_attrs;};
#define __ATTR(...) {{0}}
#define late_initcall(x)
static int capable(int x){return 1;}
static int mutex_trylock(int *p){if(lock_busy)return 0;lock_held=1;return 1;}
static void mutex_lock(int *p){}
static void mutex_unlock(int *p){lock_held=0;}
static void usleep_range(int a,int b){}
static int sysfs_streq(const char *a,const char *b){return !strcmp(a,b);}
static u32 readl(void *p){
 u32 v;memcpy(&v,p,4);
 if((uint8_t *)p>=mca&&(uint8_t *)p<mca+4096){reads_mca++;if(p==mca+0x28||p==mca+0x3c)fifo_reads++;}
 return v;
}
static void raw(u32 v,void *p){memcpy(p,&v,4);}
static void udelay(unsigned int us){
 elapsed+=us;
 if(!no_drain&&(readl(mca+12)&2)&&(readl(mca+24)&1)){if(slow_drain){if(fifo)fifo--;}else fifo=0;raw((readl(mca+0x40)&~255U)|fifo|(fifo ? 0 : 0x1000),mca+0x40);}
}
static bool a6_power_is_idle(u32 s){return s!=U32_MAX && !(s&(A6_POWER_XIP|A6_POWER_ERR|A6_POWER_RX))&&(s&A6_POWER_TX);}
static bool a6_power_recover(void){if(amp_recover_fail)return false;raw(A6_POWER_XEN|A6_POWER_TX,i2c+0x14);return true;}
static void writel(u32 v,void *p){
 writes++;
 if(p==pmgr+0xa0||p==pmgr+0xe0||p==pmgr+0xac){
  int index=p==pmgr+0xa0?0:1;
  if((v&15)==15){if(index!=fail_enable && !(p==pmgr+0xac && fail_amp_gate))v=(v&~255U)|255;}
  else if(index==fail_restore)v=(v&~255U)|255;
 }else if((uint8_t *)p>=mca&&(uint8_t *)p<mca+4096){
  unsigned int off=(uint8_t *)p-mca;
  bool valid=off==8||off==12||off==16||off==20||off==24||off==28||off==32||off==36||off==40||off==44||off==48||off==52||off==56||off==0x40||off==0x44;
  assert(valid);
  if(off==0x28){assert(v==0);serial_writes++;fifo++;raw((readl(mca+0x40)&~255U)|fifo,mca+0x40);if(fifo>128)raw(readl(mca+0x40)|0x2000,mca+0x40);return;}
  if(off==0x40){raw(readl(p)&~v,p);return;}
  if(off==0x44&&!fail_reset){v=0;fifo=0;}
 }else if((uint8_t *)p>=nco&&(uint8_t *)p<nco+4096){
  assert(p==nco+0x310||p==nco+0x314||p==nco+0x318);
  if(fail_nco&&p==nco+0x310)v|=2;
 }else if((uint8_t *)p>=acs&&(uint8_t *)p<acs+4096){assert(p==acs+0x24 || p==acs+0x18);}
 else if((uint8_t *)p>=i2c&&(uint8_t *)p<i2c+4096){
  assert(p==i2c||p==i2c+0x14);
  if(p==i2c&&v==0x601){
#ifdef A6_AUDIO_AMP_ID
  assert(lock_held && readl(gpio+42*4)==0x203 && readl(iis2)==0x136);amp_id_reads++;
#endif
  raw(amp_nack ? BIT(21) : amp_timeout ? A6_POWER_XIP : A6_POWER_XEN|A6_POWER_RX|A6_POWER_TX,i2c+0x14);raw(0xb1,i2c+4);}

 }else if((uint8_t *)p>=iis2&&(uint8_t *)p<iis2+4096){
  assert((p==iis2 || p==iis2+8 || p==iis2+0x34) && lock_held);
  if(p==iis2 && v==0x134&&!fail_iis_ack)v=0x136;
 }else if((uint8_t *)p>=audio_switch&&(uint8_t *)p<audio_switch+4096){
  assert(p==audio_switch+0x48 && lock_held);
  if((v&1)&&fail_route)return;
 }else if(p==gpio+42*4){
  assert(lock_held && (v==0x202||v==0x203));
  if(v==0x203){assert(readl(iis2)==0x136 && (readl(audio_switch+0x48)&1));if(fail_gpio_release)return;}
  if(v==0x202&&fail_gpio_restore)return;
 }else assert(0);
 raw(v,p);
}
#define readl_poll_timeout(p,v,cond,interval,timeout) ({int r=-ETIMEDOUT;for(int q=0;q<10;q++){v=readl(p);if(cond){r=0;break;}}r;})
static int sysfs_emit(char *b,const char *f,...){va_list a;va_start(a,f);int n=vsprintf(b,f,a);va_end(a);return n;}
#define sysfs_emit_at(b,n,...) sysfs_emit((b)+(n),__VA_ARGS__)
static int of_machine_is_compatible(const char *s){return 1;}
static void *ioremap(unsigned long a,int n){return mca;}
static void iounmap(void *p){}
static int sysfs_create_group(void *p,const void *q){return 0;}

#include "../kernel/platform/a6-audio-fifo-discover.inc"
static void setup(void){
 memset(a6_memory_capture_copy,0,sizeof(a6_memory_capture_copy));a6_memory_capture_copy[0]=0x41364d31;a6_memory_capture_copy[1]=1;a6_memory_capture_copy[25]=5;a6_memory_capture_copy[26]=a6_memory_capture_copy[27]=1;a6_memory_capture_copy[28]=384;a6_memory_capture_copy[452]=24000000;
 memset(pmgr,0,sizeof(pmgr));memset(mca,0,sizeof(mca));memset(nco,0,sizeof(nco));memset(acs,0,sizeof(acs));memset(i2c,0,sizeof(i2c));
 a6_af_mca=mca;a6_af_nco=nco;a6_af_acs=acs;
 a6_af_attempted=false;a6_af_polls=a6_af_peak=0;a6_af_snaps=a6_af_written=a6_af_source=a6_af_nsteps=0;a6_af_result=a6_af_cleanup=0;a6_af_amp=-EAGAIN;
 memset(a6_af_fault,0,sizeof(a6_af_fault));writes=reads_mca=lock_busy=serial_writes=fifo_reads=fifo=elapsed=0;fail_enable=fail_restore=-1;fail_nco=fail_reset=no_drain=slow_drain=0;
 raw(0x00800080,mca+4);raw(0x92000800,nco+0x2b0);raw(24000000,nco+0x2b4);raw(0,nco+0x2b8);raw(1,acs+0x24);
 raw(0x2ff,pmgr+0x118);raw(A6_POWER_TX,i2c+0x14);raw(0x104,i2c+0x1c);raw(1,i2c+0x28);raw(1,gpio+42*4);
}
static int run(void){return a6_af_run(0,0,"silent-fifo-enable-restore",25);}
#ifndef A6_AUDIO_AMP_ID
int main(void){
 setup();assert(run()==25);assert(serial_writes==256&&a6_af_written==256&&a6_af_snaps==11&&!fifo_reads);assert(a6_af_amp==0&&a6_af_amp_id==0xb1);assert(readl(pmgr+0xa0)==0&&readl(pmgr+0xe0)==0&&readl(acs+0x24)==1&&readl(nco+0x310)==0);char status[4096];assert(a6_af_status(0,0,status)<4096);char chunk[512];assert(a6_af_dumps(0,0,0,chunk,0,512)==512);assert(a6_af_dumps(0,0,0,chunk,11*4096,512)==0);assert(run()==-EALREADY);
 for(int f=0;f<2;f++){setup();fail_enable=f;assert(run()==-ETIMEDOUT);assert(!reads_mca&&!serial_writes);assert(readl(pmgr+0xa0)==0&&readl(pmgr+0xe0)==0);}
 setup();raw(2,mca+12);assert(run()==-EBUSY&&!serial_writes);
 setup();raw(0,nco+0x2b0);assert(run()==25&&serial_writes==256);
 setup();raw(0,nco+0x2b0);a6_memory_capture_copy[452]=342000000;assert(run()==25&&a6_af_source==342000000);
 setup();a6_memory_capture_copy[452]=0;assert(run()==-ENODATA&&!serial_writes&&readl(pmgr+0xa0)==0);
 setup();a6_memory_capture_copy[452]=342000000;assert(run()==-EINVAL&&!serial_writes);
 setup();fail_nco=1;assert(run()==-EUCLEAN&&!serial_writes);
 setup();fail_reset=1;assert(run()==-EUCLEAN&&!serial_writes&&readl(pmgr+0xa0)==0);
 setup();raw(0,gpio+42*4);assert(run()==25&&a6_af_amp==-EHOSTDOWN);
 setup();raw(A6_POWER_XIP,i2c+0x14);assert(run()==25&&a6_af_amp==-EBUSY);
 setup();slow_drain=1;assert(run()==25&&serial_writes==256&&a6_af_polls>0&&a6_af_peak<=112&&!(a6_af_fault[2][1]&0x2000));
 setup();no_drain=1;assert(run()==-ETIMEDOUT&&serial_writes==112&&a6_af_peak==112&&a6_af_cleanup==0);
 setup();lock_busy=1;assert(run()==-EBUSY&&!writes&&!a6_af_attempted);
 puts("PASS: actual handler, zero-only bounded FIFO writes, data-port exclusions, exact restores, gate/NCO/reset faults, active stream refusal, no clock guess, locked amp read and skip paths");
}

#else
static void amp_setup(void){
 setup();memset(iis2,0,sizeof(iis2));memset(audio_switch,0,sizeof(audio_switch));
 a6_ai_iis=iis2;a6_ai_switch=audio_switch;
 memset(a6_ai_gate,0,sizeof(a6_ai_gate));memset(a6_ai_regs,0,sizeof(a6_ai_regs));memset(a6_ai_reset,0,sizeof(a6_ai_reset));
 a6_ai_stage=0;a6_ai_result=-EAGAIN;fail_amp_gate=fail_iis_ack=fail_gpio_release=fail_gpio_restore=fail_route=amp_nack=amp_timeout=amp_recover_fail=amp_id_reads=0;
 a6_memory_capture_copy[480]=3;a6_memory_capture_copy[481]=1;a6_memory_capture_copy[482]=4;a6_memory_capture_copy[483]=24000000;a6_memory_capture_copy[484]=0;a6_memory_capture_copy[485]=1;
 raw(0x202,gpio+42*4);raw(0x200,pmgr+0xa0);raw(0x200,pmgr+0xac);raw(1,acs+0x18);raw(0x80010000,nco+0x2d0);
}
static void restored(void){assert(!lock_held);assert(readl(gpio+42*4)==0x202);assert(readl(iis2)==0);assert(readl(audio_switch+0x48)==0);assert(readl(acs+0x18)==1);assert(readl(pmgr+0xac)==0x200);assert(readl(pmgr+0xa0)==0x200);assert(readl(nco+0x2d0)==0x80010000);}
int main(void){
 amp_setup();assert(run()==25 && a6_ai_result==0 && a6_af_amp_id==0xb1 && amp_id_reads==1);assert(a6_ai_stage==4);restored();char status[4096];assert(a6_af_status(0,0,status)<4096);
 amp_setup();raw(0x22,iis2);raw(0x01f80000,iis2+8);raw(0x01f80000,iis2+0x34);assert(run()==25 && a6_ai_result==0 && amp_id_reads==1);assert(readl(iis2)==0x22 && readl(iis2+8)==0x01f80000 && readl(iis2+0x34)==0x01f80000 && readl(gpio+42*4)==0x202 && !lock_held);
 amp_setup();raw(0x22,iis2);raw(0x01f80006,iis2+8);raw(0x01f80000,iis2+0x34);assert(run()==25 && a6_ai_result==-EBUSY && !amp_id_reads && readl(iis2+8)==0x01f80006);
 amp_setup();amp_nack=1;assert(run()==25 && a6_ai_result==-ENXIO && amp_id_reads==1);restored();
 amp_setup();amp_timeout=1;assert(run()==25 && a6_ai_result==-ETIMEDOUT && amp_id_reads==1);restored();
 amp_setup();fail_amp_gate=1;assert(run()==25 && a6_ai_result==-ETIMEDOUT && !amp_id_reads);restored();
 amp_setup();fail_iis_ack=1;assert(run()==25 && a6_ai_result==-ETIMEDOUT && !amp_id_reads);restored();
 amp_setup();fail_gpio_release=1;assert(run()==25 && a6_ai_result==-EIO && !amp_id_reads);restored();
 amp_setup();fail_route=1;assert(run()==25 && a6_ai_result==-EIO && !amp_id_reads);restored();
 amp_setup();amp_recover_fail=1;assert(run()==-EUCLEAN && amp_id_reads==1);restored();
 amp_setup();fail_gpio_restore=1;assert(run()==-EUCLEAN && amp_id_reads==1 && readl(gpio+42*4)==0x203 && !lock_held);assert(readl(iis2)==0 && readl(audio_switch+0x48)==0 && readl(pmgr+0xac)==0x200);
 amp_setup();a6_memory_capture_copy[483]=0;assert(run()==25 && a6_ai_result==-ERANGE && !amp_id_reads);restored();
 amp_setup();raw(A6_POWER_XIP,i2c+0x14);assert(run()==25 && a6_ai_result==-EBUSY && !amp_id_reads);restored();
 amp_setup();raw(1,iis2+8);assert(run()==25 && a6_ai_result==-EBUSY && !amp_id_reads);assert(readl(iis2+8)==1 && readl(gpio+42*4)==0x202 && readl(pmgr+0xac)==0x200);
 amp_setup();raw(0x203,gpio+42*4);assert(run()==25 && a6_ai_result==-EBUSY && !amp_id_reads && readl(gpio+42*4)==0x203);
 amp_setup();lock_busy=1;assert(run()==-EBUSY && !writes && !amp_id_reads);
 puts("PASS: amp MCLK/reset/locked ID order; NACK, timeout, gate, clock, GPIO and route failures; active state refusal; exact restore and no NCO/rail/amp writes");
}
#endif

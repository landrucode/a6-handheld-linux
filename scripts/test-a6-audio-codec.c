// SPDX-License-Identifier: GPL-2.0-only
/* Actual codec handler: bus ownership, real framing, partial failure restore. */
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/types.h>
typedef uint32_t u32;typedef uint8_t u8;typedef uint16_t u16;typedef int16_t s16;typedef uint64_t u64;
#define A6_AUDIO_CODEC_TEST
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(a[0]))
#define CLOCK_MONOTONIC 1
#define HRTIMER_MODE_REL 0
#define ms_to_ktime(v) ((v)*1000)
#define __iomem
#define U32_MAX UINT32_MAX
#define CAP_SYS_RAWIO 1
struct kobject{};struct kobj_attribute{int attr;};
#define __ATTR(...) {0}
static u8 mca[4096];static void *a6_af_mca=mca;
static bool a6_at_codec,a6_at_feeding,a6_at_wave,a6_at_reference;
static unsigned int a6_at_variant,model_amp_at;static int a6_ai_result,model_amp_error;
static void a6_af_read_amp(void);
static unsigned int a6_at_samples,a6_at_peak=32,a6_at_elapsed_us,a6_at_mv[3],a6_at_min_mv;
static u32 a6_at_status_after;static u64 a6_at_wave_start;
static int a6_at_expired;static unsigned int model_time,model_fifo,model_fraction,model_words,model_peak,model_transactions,model_failed;
static unsigned int model_fail_transfer,model_wrong_transfer,model_spi_ready;static bool model_no_drain,model_timer_early;
static u8 model_codec[65536],model_baseline[65536];
static const signed char a6_at_sine[48]={0,1,2,3,4,5,6,6,7,7,8,8,8,8,8,7,7,6,6,5,4,3,2,1,0,-1,-2,-3,-4,-5,-6,-6,-7,-7,-8,-8,-8,-8,-8,-7,-7,-6,-6,-5,-4,-3,-2,-1};
static int a6_ac_feed(void);
static void atomic_set(int *p,int v){*p=v;}static int atomic_read(int *p){return *p;}
static u64 div_u64(u64 v,u32 d){return v/d;}static u64 ktime_get_ns(void){return (u64)model_time*1000;}
enum hrtimer_restart{HRTIMER_NORESTART};struct hrtimer{enum hrtimer_restart(*fn)(struct hrtimer*);};
static struct hrtimer a6_at_timer,*model_timer;static unsigned int model_deadline;
static void hrtimer_setup(struct hrtimer *t,enum hrtimer_restart(*f)(struct hrtimer*),int c,int m){t->fn=f;}
static void hrtimer_start(struct hrtimer *t,unsigned int d,int m){model_timer=t;model_deadline=model_time+d;}
static void hrtimer_cancel(struct hrtimer *t){model_timer=0;}
static u8 pmgr[4096],gpio[4096],spi[4096],iis[4096],acs[4096],sw[4096];
static void *a6_touch_pmgr=pmgr,*a6_touch_gpio=gpio,*a6_af_acs=acs,*a6_ai_switch=sw;
static bool a6_auto_fault,a6_auto_paused,a6_auto_enabled=true,a6_low_enabled=true,a6_low_triggered;
static unsigned int a6_policy_vbat_mv=4100;static int a6_policy_tbat_c=30;
static u32 a6_memory_capture_copy[704];static int a6_af_cleanup,a6_ac_cleanup,a6_touch_lock;
static bool held,cs_stuck,rx_timeout,revision_changes;
static unsigned int timeout_transfer,rx_limit=5;static int gate_fail,guard_result;
static unsigned int rx_index,tx_count,transfers,writes;static u8 tx[5],revision;
static void raw(u32 v,void *p){memcpy(p,&v,4);}
static u32 readl(void *p){
 u32 v;memcpy(&v,p,4);
 if(p==spi+8 && a6_at_codec && tx_count==5 && (model_transactions==model_fail_transfer || model_time<model_spi_ready))return 5<<6;
 if(p==spi+8 && tx_count==5 && a6_at_codec && tx[0]==0x6c)return 0;
 if(p==spi+8 && tx_count==5 && !rx_timeout && transfers!=timeout_transfer)return (rx_index<rx_limit ? rx_limit-rx_index : 0)<<11;
 if(p==spi+0x20 && a6_at_codec){assert(held && tx_count==5 && rx_index<5);unsigned int reg=(tx[1]<<8)|tx[2];return rx_index++==4 ? model_codec[reg]^(model_transactions==model_wrong_transfer?1:0) : 0;}
 if(p==spi+0x20){assert(held && tx_count==5 && rx_index<5);return rx_index++==4?(tx[1]==0 && tx[2]==5?(revision_changes && transfers==2 ? revision^1 : revision):0):0;}
 if(a6_at_codec && tx_count==5 && tx[0]==0x6c && model_time>=model_spi_ready && model_transactions!=model_fail_transfer && (p==spi+0x34 || p==spi+0x4c))return 0;
 if((p==spi+0x34 || p==spi+0x4c) && rx_index==5)return 0;
 return v;
}
static void writel(u32 v,void *p){
 assert(held);writes++;
 if(p==mca+0x40){raw(readl(p)&~v,p);return;}
 if(p==mca+0x44){raw(0,p);model_fifo=model_fraction=model_words=0;return;}
 if(p==spi+0x10){assert(readl(gpio+87*4)==0x202);assert(tx_count<5);tx[tx_count++]=v;if(tx_count==5){assert((tx[0]==0x6d || (a6_at_codec && tx[0]==0x6c)) && tx[2]<128 && !tx[3]);assert(*(u32 *)(spi+0x34)==(tx[0]==0x6c?0:5));assert(*(u32 *)(spi+0x4c)==5);transfers++;
 if(a6_at_codec){model_transactions++;model_spi_ready=model_time+1700;if(tx[0]==0x6c){unsigned int reg=(tx[1]<<8)|tx[2];if(reg==0x24f && !(tx[4]&0x20)){assert(model_fifo>=64);assert(readl(sw+0x10)==0xf014 && readl(sw+0x24)==0x400);assert((readl(mca+24)&1)&&(readl(mca+12)&2));}model_codec[reg]=tx[4];}}
 else assert(!tx[4]);}return;}
 if(p==spi){if(!v)rx_index=tx_count=0;raw(v,p);return;}
 if(p==spi+8){raw(0,p);return;}
 if(p==iis){raw(v==0x134?0x136:v,p);return;}
 if(p==gpio+87*4 && v==0x203 && cs_stuck)return;
 if(p>= (void *)pmgr && p<(void *)(pmgr+4096) && (v&255)==15){raw((v&~255U)|255,p);return;}
 raw(v,p);
}
static int capable(int c){return 1;}
static bool sysfs_streq(const char *a,const char *b){return !strcmp(a,b);}
static bool mutex_trylock(int *p){assert(!held);held=true;return true;}
static void mutex_lock(int *p){assert(!held);held=true;}
static void mutex_unlock(int *p){assert(held);held=false;}
static void udelay(unsigned int u){
 model_time+=u;
 if(a6_at_codec && a6_at_feeding && (readl(mca+24)&1) && (readl(mca+12)&2) && !model_no_drain){model_fraction+=u*384000;unsigned int d=model_fraction/1000000;model_fraction%=1000000;model_fifo=model_fifo>d ? model_fifo-d : 0;raw(model_fifo|(model_fifo?0:0x1000),mca+0x40);}
 if(model_timer && (model_time>=model_deadline || model_timer_early)){model_timer->fn(model_timer);model_timer=0;}
}
static void writew(u16 v,void *p){assert(held && p==mca+0x28 && model_fifo<128);unsigned int mag=(s16)v<0?-(int)(s16)v:(s16)v;assert(mag<=32);if(model_words%8!=2)assert(!v);if(mag>model_peak)model_peak=mag;model_words++;model_fifo++;raw((readl(mca+0x40)&~255U)|model_fifo,mca+0x40);}
static int a6_at_wait(unsigned int ms){for(unsigned int i=0;i<ms*100;i++){int r=a6_ac_feed();if(r)return r;udelay(10);}return 0;}
static int a6_at_voltage(unsigned int i){int r=a6_at_wait(10);if(r)return r;a6_at_mv[i]=4100;a6_at_min_mv=4100;return 0;}
#include "../build/audio-research/codec-receiver-sequence.private.inc"

static void usleep_range(unsigned int a,unsigned int b){}

static int a6_af_poll(void *p,u32 mask,u32 want){if(gate_fail && p==pmgr+(gate_fail==1?0xa0:gate_fail==2?0xa4:0xf0) && want==255)return -ETIMEDOUT;return (readl(p)&mask)==want?0:-ETIMEDOUT;}
static int sysfs_emit(char *b,const char *f,...){return 0;}
#define sysfs_emit_at(...) 0
#include "../kernel/platform/a6-audio-codec.inc"
static void a6_af_read_amp(void){assert(!a6_at_codec && held);assert(model_codec[0x2e]==0x80 && !model_codec[0x2f] && (model_codec[0x24f]&0xa0)==0xa0);model_amp_at=model_transactions;a6_ai_result=model_amp_error;}
static void setup(void){
 memset(pmgr,0,sizeof(pmgr));memset(gpio,0,sizeof(gpio));memset(spi,0,sizeof(spi));memset(iis,0,sizeof(iis));memset(acs,0,sizeof(acs));memset(sw,0,sizeof(sw));
 memset(mca,0,sizeof(mca));memset(model_codec,0,sizeof(model_codec));model_codec[5]=0xb1;model_codec[6]=0x25;model_codec[7]=4;model_codec[0x10]=0xc0;model_codec[0x13]=model_codec[0x2e]=0xd0;model_codec[0x242]=0x2b;model_codec[0x24f]=0xe0;model_codec[0xc804]=0x45;
 memcpy(model_baseline,model_codec,sizeof(model_baseline));model_time=model_fifo=model_fraction=model_words=model_peak=model_transactions=model_failed=model_fail_transfer=model_wrong_transfer=0;model_timer=0;model_no_drain=model_timer_early=false;a6_at_codec=a6_at_feeding=a6_at_wave=a6_at_reference=false;a6_at_variant=0;model_amp_at=0;model_amp_error=0;a6_at_expired=0;a6_at_samples=0;memset(a6_at_mv,0,sizeof(a6_at_mv));a6_ac_play_attempted=false;a6_ac_preimages=0;
 raw(0x202,gpio+42*4);raw(0x208,mca+24);raw(0x0f107005,mca+12);
 a6_ac_spi=spi;a6_ac_iis=iis;a6_ac_cleanup=a6_af_cleanup=0;held=cs_stuck=rx_timeout=revision_changes=false;timeout_transfer=0;rx_limit=5;gate_fail=guard_result=0;writes=transfers=tx_count=rx_index=0;revision=0xa0;
 a6_auto_fault=a6_auto_paused=a6_low_triggered=false;a6_auto_enabled=a6_low_enabled=true;a6_policy_vbat_mv=4100;a6_policy_tbat_c=30;a6_memory_capture_copy[483]=24000000;
 raw(0x202,gpio+87*4);raw(8,spi+4);raw(3,spi+12);raw(1,spi+0x30);
 raw(0x22,iis);raw(0x01f80000,iis+8);raw(0x01f80000,iis+0x34);
}
static void restored(void){
 assert(!held && !a6_ac_cleanup);assert(readl(gpio+87*4)==0x202);
 assert(readl(iis)==0x22 && readl(iis+8)==0x01f80000 && readl(iis+0x34)==0x01f80000);
 assert(!readl(acs+0x10) && !readl(sw+0x40));assert(!readl(pmgr+0xa0)&&!readl(pmgr+0xa4)&&!readl(pmgr+0xf0));
 assert(!readl(spi)&&readl(spi+4)==8&&readl(spi+12)==3&&readl(spi+0x30)==1&&!readl(spi+0x34)&&!readl(spi+0x4c));
}
int main(void){
 const char *command="codec-id-enable-restore";
 setup();assert(a6_ac_run(0,0,command,23)==23);assert(transfers==16 && a6_ac_control_reads==13 && a6_ac_reads==3 && a6_ac_reply[2][4]==0xa0);restored();
 setup();rx_timeout=true;assert(a6_ac_run(0,0,command,23)==-ETIMEDOUT);restored();assert(transfers==1&&!a6_ac_reads);
 setup();revision=255;assert(a6_ac_run(0,0,command,23)==-ENODEV);restored();
 for(int gate=1;gate<=3;gate++){setup();gate_fail=gate;assert(a6_ac_run(0,0,command,23)==-ETIMEDOUT);restored();assert(!transfers);}
 for(unsigned int limit=0;limit<5;limit++){setup();rx_limit=limit;assert(a6_ac_run(0,0,command,23)==-ETIMEDOUT);restored();}
 for(unsigned int at=1;at<=16;at++){setup();timeout_transfer=at;assert(a6_ac_run(0,0,command,23)==-ETIMEDOUT);restored();}
 setup();revision_changes=true;assert(a6_ac_run(0,0,command,23)==-ENODEV);assert(transfers==3);restored();
 setup();raw(1,spi);assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!transfers&&!a6_ac_cleanup);assert(!readl(pmgr+0xa0)&&!readl(pmgr+0xa4)&&!readl(pmgr+0xf0));
 setup();a6_policy_vbat_mv=3599;assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!writes);restored();
 setup();a6_auto_fault=true;assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!writes);restored();
 setup();a6_low_enabled=false;assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!writes);restored();
 setup();a6_policy_tbat_c=36;assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!writes);restored();
 setup();a6_auto_paused=true;assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!writes);restored();
 setup();a6_auto_enabled=false;assert(a6_ac_run(0,0,command,23)==-EBUSY);assert(!writes);restored();
 setup();a6_ac_cleanup=-EUCLEAN;assert(a6_ac_run(0,0,command,23)==-EUCLEAN);assert(!writes && !held);
 setup();cs_stuck=true;assert(a6_ac_run(0,0,command,23)==-EIO);restored();assert(!transfers);
 setup();a6_at_codec=true;held=true;assert(a6_ac_execute_locked(true)==0);held=false;restored();assert(a6_ac_output_enabled && a6_at_samples>47000 && model_peak==32 && a6_ac_drain_rate>=375000 && a6_ac_drain_rate<=395000);assert(!memcmp(model_codec,model_baseline,sizeof(model_codec)));assert(!readl(sw+0x10)&&!readl(sw+0x24)&&!model_timer&&!a6_at_feeding&&!a6_at_wave);
 unsigned int total=model_transactions;
 for(unsigned int fail=1;fail<=total;fail++){
  setup();a6_at_codec=true;held=true;model_fail_transfer=fail;int result=a6_ac_execute_locked(true);held=false;assert(result<0);int cleanup=a6_ac_cleanup;assert(cleanup==0 || (cleanup==-EUCLEAN && result==-EUCLEAN));a6_ac_cleanup=0;restored();a6_ac_cleanup=cleanup;if(cleanup){held=true;assert(a6_ac_execute_locked(true)==-EUCLEAN);held=false;}assert(!memcmp(model_codec,model_baseline,sizeof(model_codec)));assert(!readl(sw+0x10)&&!readl(sw+0x24)&&!model_timer&&!a6_at_feeding&&!a6_at_wave);
 }
 setup();a6_at_codec=true;held=true;model_no_drain=true;assert(a6_ac_execute_locked(true)<0);held=false;restored();assert(!a6_ac_output_enabled && !memcmp(model_codec,model_baseline,sizeof(model_codec)));
 setup();a6_at_codec=true;held=true;model_timer_early=true;assert(a6_ac_execute_locked(true)<0);held=false;restored();assert(!memcmp(model_codec,model_baseline,sizeof(model_codec)));
 setup();a6_at_codec=a6_at_reference=true;held=true;assert(a6_ac_execute_locked(true)==0);held=false;restored();assert(!a6_ac_output_enabled && !a6_at_samples && !memcmp(model_codec,model_baseline,sizeof(model_codec)));unsigned int ref_total=model_transactions,ref_amp_at=model_amp_at;
 for(unsigned int fail=1;fail<=ref_total;fail++){setup();a6_at_codec=a6_at_reference=true;held=true;model_fail_transfer=fail;int result=a6_ac_execute_locked(true);held=false;assert(result<0);int cleanup=a6_ac_cleanup;a6_ac_cleanup=0;restored();a6_ac_cleanup=cleanup;assert(!a6_ac_output_enabled && !memcmp(model_codec,model_baseline,sizeof(model_codec)));}
 setup();a6_at_codec=a6_at_reference=true;held=true;model_wrong_transfer=ref_amp_at-3;assert(a6_ac_execute_locked(true)<0);held=false;restored();assert(!model_amp_at && !memcmp(model_codec,model_baseline,sizeof(model_codec)));
 setup();a6_at_codec=a6_at_reference=true;held=true;model_amp_error=-EIO;assert(a6_ac_execute_locked(true)==-EIO);held=false;restored();assert(!memcmp(model_codec,model_baseline,sizeof(model_codec)));
 puts("PASS: codec XSP role refusal, combined amp failure restore; receiver stock setup, eight-slot packing, quiet ramp, every-transfer failure rollback, empty/drain and watchdog; ID protocol, three consistent reads, bus/gate/guard refusal, SPI timeout and exact restore");
}

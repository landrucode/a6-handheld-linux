// SPDX-License-Identifier: GPL-2.0-only
/* Actual tone handler with a clock/FIFO/I2C/ADC/watchdog model. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;typedef uint16_t u16;typedef int16_t s16;
#define BIT(n) (1U<<(n))
#define U32_MAX UINT32_MAX
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(a[0]))
#define min(a,b) ((a)<(b)?(a):(b))
#define A6_AUDIO_TONE_TEST
#define A6_POWER_XIP BIT(28)
#define A6_POWER_XEN BIT(27)
#define A6_POWER_TX BIT(16)
#define A6_POWER_RX BIT(19)
#define A6_POWER_ERR (BIT(21)|BIT(24))
#define CLOCK_MONOTONIC 1
#define HRTIMER_MODE_REL 0
#define ms_to_ktime(a) ((a)*1000)
typedef int atomic_t;
#define ATOMIC_INIT(a) (a)
static void atomic_set(atomic_t *p,int v){*p=v;}
static int atomic_read(atomic_t *p){return *p;}
enum hrtimer_restart {HRTIMER_NORESTART};
struct hrtimer {enum hrtimer_restart (*function)(struct hrtimer *);};
static struct hrtimer *timer;static unsigned int now,deadline;
static void hrtimer_setup(struct hrtimer *t,enum hrtimer_restart (*fn)(struct hrtimer *),int c,int m){t->function=fn;}
static void hrtimer_start(struct hrtimer *t,int d,int m){timer=t;deadline=now+d;}
static void hrtimer_cancel(struct hrtimer *t){timer=0;}
static u64 div_u64(u64 n,u32 d){return n/d;}
static u64 ktime_get_ns(void){return (u64)now*1000;}
static u8 gpio[4096],i2c[4096],mca[4096],sw[4096],amp[256],pmu[256];
static void *a6_touch_gpio=gpio,*a6_touch_i2c=i2c,*a6_af_mca=mca,*a6_ai_switch=sw;
static u32 a6_memory_capture_copy[704],a6_af_amp_id;
static int a6_af_cleanup,a6_policy_tbat_c=31;
static bool a6_auto_enabled=true,a6_auto_fault,a6_auto_paused,a6_low_enabled=true,a6_low_triggered;
static unsigned int a6_policy_vbat_mv=4100;
static unsigned int model_hz=48000,model_phase,delay_scale=1;
static unsigned int a6_at_variant, a6_at_peak;
static bool a6_at_supplies,a6_at_ios_route;
static unsigned int rx_enable_writes,rx_reads;
static unsigned int rx_fifo,rx_frames,rx_fraction;static int rx_stall;
static unsigned int observed_peak;
static unsigned int fifo,frames,transactions,regwrites;static int fail_at,wrong_at,no_drain,forced_under,forced_over,timer_early;
static u32 pending;static unsigned int addr,reg,state;static bool is_read;
static unsigned int gpio_delay,gpio_ready[2],gpio_fall_delay,gpio_fall_ready[2];static bool gpio_stuck;
static u32 readl(void *p){u32 v;memcpy(&v,p,4);for(unsigned int i=0;i<2;i++)if(p==gpio+(90+i)*4 && (v&1) && (gpio_stuck || now<gpio_ready[i]))v&=~1U;for(unsigned int i=0;i<2;i++)if(p==gpio+(90+i)*4 && !(v&1) && now<gpio_fall_ready[i])v|=1;return v;}
static void raw(u32 v,void *p){memcpy(p,&v,4);}
static bool a6_power_is_idle(u32 s){return !(s&(A6_POWER_XIP|A6_POWER_ERR|A6_POWER_RX)) && (s&A6_POWER_TX);}
static bool a6_power_recover(void){raw(A6_POWER_TX,i2c+0x14);return true;}
static void finish(void){
 transactions++;pending=transactions==(unsigned)fail_at ? BIT(21) : A6_POWER_TX|A6_POWER_XEN|(is_read?A6_POWER_RX:0);
 /* First hardware read may still show TX-ready from the old transfer. */
 raw(A6_POWER_TX,i2c+0x14);
}
static void writel(u32 v,void *p){
 if(p==mca+0x2c && (v&1)){assert(!a6_at_ios_route);rx_enable_writes++;}
 if(p==mca+0x44){fifo=frames=model_phase=0;raw(0,p);return;}
 for(unsigned int i=0;i<2;i++)if(p==gpio+(90+i)*4){gpio_fall_ready[i]=(!(v&1) && (readl(p)&1))?now+gpio_fall_delay:0;gpio_ready[i]=(v&1)?now+gpio_delay:0;}
 if(p==mca+0x40){raw(readl(p)&~v,p);return;}
 if(p==i2c){
  if(v&0x100 && !(v&0x600)){addr=(v&255)>>1;is_read=v&1;if(!is_read)state=1;return;}
  if(v==0x601){u8 rb=(addr==0x40?amp:pmu)[reg];if(transactions+1==(unsigned)wrong_at)rb^=1;raw(rb,i2c+4);finish();return;}
  if(state==1){reg=v&255;state=2;if(v&0x200)state=3;return;}
  if(state==2){assert(v&0x200);(addr==0x40?amp:pmu)[reg]=v&255;regwrites++;if(addr==0x40 && reg==6 && !(v&0x80)){assert(fifo>=64);assert(readl(sw+8)==(a6_at_variant&4 ? 0x1000f000U : 0x1000f014U) && readl(sw+0x24)==(a6_at_ios_route ? 2U : (a6_at_variant&4 ? 0x10000202U : 0x10000200U)));}finish();return;}
  assert(0);
 }
 raw(v,p);
}
static u16 readw(void *p){assert(!a6_at_ios_route);rx_reads++;assert(p==mca+0x3c && rx_fifo);rx_fifo--;raw((readl(mca+0x40)&~0xff0000U)|(rx_fifo<<16),mca+0x40);rx_frames++;return rx_frames%2 ? 7 : 9;}
static bool a6_at_reference,a6_at_all_slots;
static s16 model_frame_sample;
static int a6_af_poll(void *p,u32 mask,u32 want){return (readl(p)&mask)==want ? 0 : -EIO;}
static void writew(u16 v,void *p){assert(p==mca+0x28);assert((s16)v>=-(int)a6_at_peak && (s16)v<=(int)a6_at_peak);assert(fifo<128);unsigned int magnitude=(s16)v<0?-(int)(s16)v:(s16)v;if(magnitude>observed_peak)observed_peak=magnitude;if(a6_at_reference && frames%8)assert(!v);if(a6_at_all_slots){if(!(frames%8))model_frame_sample=(s16)v;else assert((s16)v==model_frame_sample);}fifo++;frames++;raw((readl(mca+0x40)&~255U)|fifo,mca+0x40);}
static void udelay(unsigned int us){
 us/=delay_scale;now+=us;if(pending){raw(pending,i2c+0x14);pending=0;}if(timer && (now>=deadline || timer_early)){timer->function(timer);timer=0;}
 if(!no_drain){model_phase+=us*model_hz;unsigned int drain=model_phase/1000000;model_phase%=1000000;fifo=fifo>drain?fifo-drain:0;}
 if((readl(mca+0x2c)&1) && !rx_stall){rx_fraction+=us*(a6_at_reference?384000:(a6_at_supplies?192000:96000));rx_fifo+=rx_fraction/1000000;rx_fraction%=1000000;if(rx_fifo>128)rx_fifo=128;}
 raw((rx_fifo<<16)|fifo|(fifo?0:0x1000)|(forced_over?0x2000:0)|(forced_under?0x1000:0),mca+0x40);
}
#include "../build/audio-research/amp-tone-sequence.private.inc"
#include "../kernel/platform/a6-audio-tone.inc"
static void setup(void){
 a6_at_reset_run();rx_enable_writes=rx_reads=0;a6_at_variant=0;observed_peak=0;gpio_delay=0;gpio_fall_delay=0;gpio_stuck=false;memset(gpio_ready,0,sizeof(gpio_ready));memset(gpio_fall_ready,0,sizeof(gpio_fall_ready));
 memset(gpio,0,sizeof(gpio));memset(i2c,0,sizeof(i2c));memset(mca,0,sizeof(mca));memset(sw,0,sizeof(sw));memset(amp,0,sizeof(amp));memset(pmu,0,sizeof(pmu));memset(a6_at_routes,0,sizeof(a6_at_routes));memset(a6_at_mv,0,sizeof(a6_at_mv));
 memset(a6_memory_capture_copy,0,sizeof(a6_memory_capture_copy));a6_memory_capture_copy[512]=0x53504431;a6_memory_capture_copy[513]=1;a6_memory_capture_copy[514]=1;a6_memory_capture_copy[515]=20;memcpy((u8 *)a6_memory_capture_copy+0x820,a6_at_config,20);
 raw(0x203,gpio+42*4);raw(A6_POWER_TX,i2c+0x14);raw(0x1000,mca+0x40);raw(0x10000000,sw+8);raw(0x10000000,sw+0x24);pmu[0x48]=0x80;pmu[0x49]=0;pmu[0x4a]=220;
 rx_fifo=rx_frames=rx_fraction=0;rx_stall=0;raw(0x10a,mca+0x2c);model_hz=48000;model_phase=0;delay_scale=1;a6_af_amp_id=0xb0;a6_at_count=a6_at_samples=a6_at_min_mv=a6_at_drain_hz=a6_at_elapsed_us=0;a6_at_feeding=a6_at_wave=false;a6_af_cleanup=0;now=deadline=fifo=frames=transactions=regwrites=pending=0;timer=0;fail_at=wrong_at=no_drain=forced_under=forced_over=timer_early=0;atomic_set(&a6_at_expired,0);
}
static void restored(void){assert(readl(gpio+42*4)==0x202);assert(readl(gpio+9*4)==0);assert(!a6_at_alive_active && !a6_at_rx_active);assert(readl(mca+0x2c)==0x10a);assert(readl(sw+8)==0x10000000);assert(readl(sw+0x24)==0x10000000);assert(pmu[0x48]==0x80);assert(!timer&&!a6_at_feeding&&!a6_at_wave);}
static int play_success(void){int ret=a6_at_play();assert(ret==0 && a6_af_cleanup==0);return ret;}
int main(void){
 setup();a6_at_feeding=true;a6_at_rx_active=true;raw(0x04000000,mca+0x40);assert(a6_at_feed()==0);raw(0x20000000,mca+0x40);assert(a6_at_feed()==-EOVERFLOW);
 setup();delay_scale=5;a6_at_feeding=true;assert(a6_at_feed()==0);unsigned int wait_start=now;assert(a6_at_wait(10)==0);assert(now-wait_start>=10000 && now-wait_start<10100);a6_at_feeding=false;
 setup();assert(play_success()==0);restored();assert(a6_at_samples>0 && a6_at_elapsed_us>=1000000 && a6_at_elapsed_us<1010000 && a6_at_count>60 && a6_at_mv[1]>3600 && a6_at_mv[2]>3600);unsigned int total=transactions;
 setup();a6_at_variant=3;gpio_delay=20000;assert(play_success()==0);restored();assert(a6_at_ext_observed[0]==3 && a6_at_ext_observed[1]==3);
 setup();a6_at_variant=3;gpio_fall_delay=20000;assert(play_success()==0);restored();gpio_fall_delay=0;
 setup();a6_at_variant=3;gpio_stuck=true;assert(a6_at_play()==-EIO);restored();assert(!transactions && !a6_at_samples && a6_at_ext_observed[0]==2);assert(readl(gpio+90*4)==0 && readl(gpio+91*4)==0);
 for(unsigned int role=0;role<2;role++){setup();a6_at_variant=role?4:0;a6_at_peak=512;a6_at_supplies=true;assert(play_success()==0);restored();assert(amp[0x2f]==6 && amp[0x30]==8);assert(amp[0x34]==3 && amp[0x35]==255);assert(a6_at_play_state[1]==0);assert(observed_peak==512);for(unsigned int stage=0;stage<3;stage++)assert(a6_at_monitor_count[stage]==512 && a6_at_monitor_phase[stage]<(a6_at_supplies?4:2));}
 for(unsigned int role=0;role<2;role++){setup();a6_at_variant=role?4:0;a6_at_peak=512;assert(play_success()==0);restored();assert(a6_at_samples>47000 && a6_at_samples<=48000 && observed_peak==512);assert(amp[0x10]==0x19 && (amp[0x12]&0xf0)==0x70);for(unsigned int stage=0;stage<3;stage++)assert(a6_at_monitor_count[stage]==512 && a6_at_monitor_phase[stage]<(a6_at_supplies?4:2));}
 for(unsigned int variant=0;variant<8;variant++){setup();a6_at_variant=variant;assert(play_success()==0);restored();for(unsigned int g=0;g<2;g++){assert(readl(gpio+(90+g)*4)==0);assert(a6_at_ext[g][1]==(2|((variant>>g)&1)));}assert(a6_at_play_state[3]==((variant&4)?0x43:3));for(unsigned int stage=0;stage<3;stage++)assert(a6_at_monitor_count[stage]>100);}
 setup();assert(play_success()==0);restored();
 assert(a6_at_rx_count>1000 && a6_at_rx_nonzero==a6_at_rx_count && a6_at_rx_peak<=128);assert(a6_at_alive_edges>=50);a6_at_reset_run();assert(!a6_at_count && !a6_at_samples && !a6_at_mv[1]);raw(0x203,gpio+42*4);assert(play_success()==0);restored();assert(a6_at_elapsed_us>=1000000 && a6_at_count>60 && a6_at_mv[1]>3600);
 setup();raw(0xabcdef02,gpio+9*4);assert(play_success()==0);assert(readl(gpio+9*4)==0xabcdef02);assert(a6_at_alive[2]==a6_at_alive[0]);raw(0,gpio+9*4);restored();
 setup();delay_scale=5;assert(play_success()==0);restored();assert(a6_at_elapsed_us>=1000000 && a6_at_elapsed_us<1010000 && a6_at_mv[1]>3600 && a6_at_mv[2]>3600);
 setup();model_hz=8000;assert(play_success()==0);restored();assert(a6_at_elapsed_us>=1000000 && a6_at_elapsed_us<1010000 && a6_at_samples<10000 && a6_at_mv[1]>3600 && a6_at_mv[2]>3600);
 setup();amp[0x15]=0x10;amp[0x16]=0x20;assert(play_success()==0);restored();assert(amp[0x0d]==3);for(unsigned int n=0;n<3;n++){assert(a6_at_faults[n][0]==0x10 && a6_at_faults[n][1]==0x10 && a6_at_faults[n][2]==0x20 && a6_at_faults[n][3]==0x20);}
 for(unsigned int n=1;n<=total;n++){setup();fail_at=n;assert(a6_at_play()<0);restored();}
 setup();rx_stall=1;assert(play_success()==0);restored();assert(!a6_at_rx_count);
 setup();wrong_at=10;assert(a6_at_play()<0);restored();
 setup();pmu[0x4a]=100;assert(a6_at_play()==-ERANGE);restored();assert(!a6_at_samples);
 setup();a6_memory_capture_copy[513]|=4;a6_memory_capture_copy[517]=20;a6_memory_capture_copy[0x860/4]=1;((u8 *)a6_memory_capture_copy)[0x850]=3;((u8 *)a6_memory_capture_copy)[0x854]=2;assert(play_success()==0);restored();assert(amp[0x46]==3 && amp[0x3a]==((a6_at_config[12]&0xe0)|2));
 setup();a6_memory_capture_copy[513]|=4;a6_memory_capture_copy[517]=20;a6_memory_capture_copy[0x860/4]=2;assert(play_success()==0);restored();assert(amp[0x46]==a6_at_config[16] && amp[0x3a]==a6_at_config[12]);
 setup();((u8 *)a6_memory_capture_copy)[0x82c]=139;((u8 *)a6_memory_capture_copy)[0x830]=13;((u8 *)a6_memory_capture_copy)[0x833]=0;assert(play_success()==0);restored();assert(amp[0x3a]==139 && amp[0x46]==13 && amp[0x18]==0);
 setup();forced_under=1;assert(a6_at_play()==-EPIPE);restored();
 setup();no_drain=1;assert(a6_at_play()==-EIO);restored();
 setup();timer_early=1;assert(a6_at_play()==-ETIMEDOUT);restored();
 setup();forced_over=1;assert(a6_at_play()<0);restored();
 setup();a6_memory_capture_copy[513]=17;assert(a6_at_play()==-ENODATA && !transactions);
 setup();a6_af_amp_id=0xb1;assert(a6_at_play()==-ENODEV && !transactions);
 setup();a6_auto_fault=true;assert(a6_at_play()==-EBUSY && !transactions);a6_auto_fault=false;
 for(unsigned int variant=0;variant<8;variant++){setup();a6_at_reference=true;a6_at_variant=variant;a6_at_peak=512;model_hz=384000;assert(play_success()==0);restored();assert(a6_at_samples>47000 && a6_at_samples<=48000 && observed_peak==512);assert(a6_at_drain_hz>=47000 && a6_at_drain_hz<=49000);assert(a6_at_rx_count>384000 && a6_at_max_gap<200000);for(unsigned int stage=0;stage<3;stage++)assert(a6_at_monitor_count[stage]==512);}
 setup();a6_at_reference=true;model_hz=384000;a6_at_peak=512;assert(play_success()==0);restored();unsigned int ref_total=transactions;
 for(unsigned int fail=1;fail<=ref_total;fail++){setup();a6_at_reference=true;model_hz=384000;fail_at=fail;assert(a6_at_play()<0);restored();}
 const unsigned int ladder_peaks[]={3277,8231,16422,23197,32767};
 for(unsigned int i=0;i<ARRAY_SIZE(ladder_peaks);i++){setup();a6_at_reference=true;model_hz=384000;a6_at_peak=ladder_peaks[i];assert(play_success()==0);restored();assert(observed_peak==ladder_peaks[i] && a6_at_elapsed_us>=1000000 && a6_at_elapsed_us<1010000);assert(a6_at_samples>47000 && a6_at_rx_count>384000);}
 setup();a6_at_stock44100=true;a6_at_frame_limit=44100;a6_at_variant=4;model_hz=44100;a6_at_peak=8231;
 assert(play_success()==0);restored();assert(a6_at_samples>43900 && a6_at_samples<=44100);
 assert(a6_at_drain_hz>=43000 && a6_at_drain_hz<=45000 && observed_peak==8231);
 assert(amp[0x0d]==0x43 && amp[0x0e]==0xc4 && amp[0x2d]==0 && amp[0x2e]==2);
 assert(a6_at_power_state[0][3]==5 && a6_at_power_state[0][5]==2 && a6_at_alive_edges>=50);
 for(unsigned int stage=0;stage<3;stage++)assert(a6_at_power_state[stage][0]==0 && a6_at_power_state[stage][1]==0x30);
 unsigned int stock_total=transactions;
 for(unsigned int fail=1;fail<=stock_total;fail++){setup();a6_at_stock44100=true;a6_at_frame_limit=44100;a6_at_variant=4;model_hz=44100;fail_at=fail;assert(a6_at_play()<0);restored();}
 setup();a6_at_stock44100=true;a6_at_frame_limit=44100;a6_at_variant=4;model_hz=48000;assert(a6_at_play()==-ERANGE);restored();assert(!a6_at_samples);
 for(unsigned int state=0;state<4;state++){setup();a6_at_stock44100=true;a6_at_frame_limit=44100;a6_at_variant=4|state;model_hz=44100;a6_at_peak=32767;assert(play_success()==0);restored();assert(a6_at_elapsed_us>=1000000 && observed_peak==32767);for(unsigned int pin=0;pin<2;pin++)assert(a6_at_ext_observed[pin]==(2|((state>>pin)&1)));}
 setup();a6_at_stock44100=a6_at_all_slots=true;a6_at_frame_limit=44100;a6_at_variant=4;model_hz=352800;a6_at_peak=32767;
 assert(play_success()==0);restored();assert(a6_at_samples>43900 && a6_at_samples<=44100 && observed_peak==32767);
 unsigned int all_total=transactions;
 for(unsigned int fail=1;fail<=all_total;fail++){setup();a6_at_stock44100=a6_at_all_slots=true;a6_at_frame_limit=44100;a6_at_variant=4;model_hz=352800;fail_at=fail;assert(a6_at_play()<0);restored();}
 for(unsigned int burst=1;burst<=2;burst++) {
  setup();a6_at_stock44100=a6_at_ios_route=true;a6_at_ios_amp=burst==2;a6_at_frame_limit=burst==2?48000:44100;a6_at_variant=4;model_hz=a6_at_frame_limit;a6_at_peak=32767;
  assert(play_success()==0);restored();assert(!rx_enable_writes && !rx_reads && !a6_at_rx_count);assert(a6_at_routes[1][1]==2);
  assert(observed_peak==32767 && a6_at_elapsed_us>=1000000);assert(a6_at_samples>a6_at_frame_limit-200 && a6_at_samples<=a6_at_frame_limit);
  for(unsigned int stage=0;stage<3;stage++){assert(!a6_at_monitor_count[stage]);assert(a6_at_power_state[stage][1]==(burst==2?0xf8:0x30));assert(a6_at_power_state[stage][2]==(burst==2?0x49:0x4b));assert(a6_at_power_state[stage][9]==(burst==2?0:0x19));}
  unsigned int ios_total=transactions;
  if(burst==2){unsigned int found=0;for(unsigned int row=0;row<a6_at_count;row++)if(a6_at_log[row][0]>=0xe0 && a6_at_log[row][0]<=0xe2){assert(a6_at_log[row][2]==a6_at_log[row][3]);found++;}assert(found==3);}
  for(unsigned int fail=1;fail<=ios_total;fail++){setup();a6_at_stock44100=a6_at_ios_route=true;a6_at_ios_amp=burst==2;a6_at_frame_limit=burst==2?48000:44100;a6_at_variant=4;model_hz=a6_at_frame_limit;fail_at=fail;assert(a6_at_play()<0);restored();assert(!rx_enable_writes && !rx_reads);}
 }
 puts("PASS: bounded quiet samples, prefill, every I2C transaction failure, watchdog, stalled drain, ADC and route restore, metadata/ID/guard refusal");
}

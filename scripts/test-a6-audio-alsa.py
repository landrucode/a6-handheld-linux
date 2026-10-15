#!/usr/bin/env python3
"""Execute the actual PCM callbacks against bounded FIFO/clock models."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'kernel/platform/a6-audio-alsa.inc').read_text()


def function(name):
    start = source.rfind('static ', 0, source.index(name + '('))
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


prefix = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
typedef uint64_t u64;typedef uint32_t u32;typedef uint16_t u16;
typedef uint8_t u8;typedef int16_t s16;typedef unsigned long snd_pcm_uframes_t;
typedef int spinlock_t;
#define __iomem
#define U32_MAX UINT32_MAX
#define READ_ONCE(x) (x)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min(a,b) ((a)<(b)?(a):(b))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define spin_lock_irqsave(l,f) ((void)(l),(f)=0)
#define spin_unlock_irqrestore(l,f) ((void)(l),(void)(f))
#define ns_to_ktime(n) (n)
#define SNDRV_PCM_TRIGGER_START 1
#define SNDRV_PCM_TRIGGER_STOP 2
enum hrtimer_restart {HRTIMER_NORESTART,HRTIMER_RESTART};
struct hrtimer {int unused;};struct work_struct {int unused;};
struct snd_pcm_control {snd_pcm_uframes_t appl_ptr;};
struct snd_pcm_runtime {void *dma_area,*private_data;struct snd_pcm_control *control;
 snd_pcm_uframes_t buffer_size,boundary,period_size;};
struct snd_pcm_substream {struct snd_pcm_runtime *runtime;};
static unsigned char mca[4096],iis[4096],gpio[4096],nco[4096];
static void *a6_af_nco=nco;static unsigned int nco_settle,nco_reads;static bool nco_stuck;
static void *a6_af_mca=mca,*a6_ac_iis=iis,*a6_touch_gpio=gpio;
static bool a6_auto_enabled=true,a6_auto_fault,a6_auto_paused,a6_low_enabled=true,a6_low_triggered;
static unsigned int a6_policy_vbat_mv=4100;static int a6_policy_tbat_c=31;
static bool a6_at_alive_active;static u32 a6_at_alive[3];static u64 a6_at_alive_time;
static u32 rx_word=0x1234abcd;
static unsigned int fifo,rx_count,periods,faults,writes;static s16 last_written;
static u64 now;
static u64 ktime_get_ns(void){return now;}
static u64 div_u64_rem(u64 v,u32 d,u32 *r){*r=v%d;return v/d;}
static u64 div64_u64_rem(u64 v,u64 d,u64 *r){*r=v%d;return v/d;}
static u32 readl(void *p){u32 v;
 if(p==nco+0x2b0){nco_reads++;if(nco_stuck || nco_settle){if(nco_settle)nco_settle--;return 0x40000002;}}if(p==mca+0x40){memcpy(&v,p,4);return (v&~255U)|fifo;}
 if(p==iis+0x3c)return (rx_count<<13)|4;
 if(p==iis+0x38){assert(rx_count);rx_count--;return rx_word;}
 memcpy(&v,p,4);return v;}
static void writel(u32 v,void *p){if(p==mca+0x40){u32 old;memcpy(&old,p,4);v=old&~v;}memcpy(p,&v,4);}
static int a6_af_poll(void *p,u32 mask,u32 want){for(unsigned int i=0;i<10;i++)if((readl(p)&mask)==want)return 0;return -ETIMEDOUT;}
static void writew(u16 v,void *p){assert(p==mca+0x28);assert(fifo<128);fifo++;writes++;last_written=(s16)v;}
static void schedule_work(struct work_struct *w){faults++;}
static void snd_pcm_period_elapsed(struct snd_pcm_substream *s){periods++;}
static void hrtimer_forward_now(struct hrtimer *t,u64 n){}
'''

tests = r'''
int main(void){
 s16 buffer[512];for(unsigned i=0;i<512;i++)buffer[i]=-12000;
 struct snd_pcm_control ctl={200};
 struct snd_pcm_runtime runtime={.dma_area=buffer,.control=&ctl,.buffer_size=256,.boundary=4096,.period_size=32};
 struct snd_pcm_substream sub={&runtime};
 struct a6_s_stream s={.sub=&sub,.ready=true};runtime.private_data=&s;
 /* NCO restore must wait for acknowledgement, but reject a stuck clock. */
 nco_settle=3;nco_reads=0;assert(!a6_s_restore_word(nco+0x2b0,0x80010000));assert(nco_reads==4);
 nco_stuck=true;assert(a6_s_restore_word(nco+0x2b0,0x80010000)==-ETIMEDOUT);nco_stuck=false;
 /* Cold-boot MCA masks are all ones. Accept only the two mask addresses. */
 writel(U32_MAX,mca+0x24);writel(U32_MAX,mca+0x38);writel(U32_MAX,mca+0x20);
 assert(a6_s_save(&s,mca+0x24)==0 && a6_s_save(&s,mca+0x38)==0);
 assert(a6_s_save(&s,mca+0x20)==-EBUSY);
 fifo=50;now=1000000;
 assert(!a6_s_trigger(&sub,SNDRV_PCM_TRIGGER_START));
 fifo-=12;now+=250000;assert(a6_s_tick(&s.timer)==HRTIMER_RESTART);
 assert(s.frames==58 && s.pos==0 && fifo==96 && last_written<0);
 fifo-=12;now+=250000;a6_s_tick(&s.timer);assert(s.pos==0);
 fifo-=12;now+=250000;a6_s_tick(&s.timer);assert(s.pos==0);
 fifo-=12;now+=250000;a6_s_tick(&s.timer);assert(s.pos==0);
 fifo-=12;now+=250000;a6_s_tick(&s.timer);assert(s.pos==10);
 assert(s.frames<=ctl.appl_ptr && fifo<=96);
 /* No reads beyond application data; period progress follows consumed data. */
 for(unsigned i=0;i<8;i++){fifo-=12;now+=250000;a6_s_tick(&s.timer);}
 assert(s.frames<=ctl.appl_ptr && periods>0);
 /* Separate watchdog resets on missed service; it never calls I2C. */
 now+=2000000;assert(a6_s_watch(&s.watchdog)==HRTIMER_NORESTART);
 assert(!s.ready && s.error==-ETIMEDOUT && readl(gpio+42*4)==0x202);
 /* Measured status uses bit13 units; two RX words sum into a saturated mono frame. */
 struct a6_s_stream cap={.sub=&sub,.ready=true,.capture=true,.running=true};
 runtime.private_data=&cap;rx_count=3;now+=250000;
 assert(a6_s_tick(&cap.timer)==HRTIMER_RESTART);
 assert(cap.pos==1 && buffer[0]==-32768 && rx_count==0 && cap.capture_half);
 rx_count=1;now+=250000;a6_s_tick(&cap.timer);assert(cap.pos==2 && !cap.capture_half);
 /* Summation preserves either active slot, polarity, and saturation. */
 assert(buffer[1]==-32768);
 cap.capture_half=true;cap.capture_left=20000;rx_word=20000;rx_count=1;now+=250000;a6_s_tick(&cap.timer);assert(buffer[2]==32767);
 cap.capture_half=true;cap.capture_left=0;rx_word=(u16)-123;rx_count=1;now+=250000;a6_s_tick(&cap.timer);assert(buffer[3]==-123);
 cap.capture_half=true;cap.capture_left=-123;rx_word=0;rx_count=1;now+=250000;a6_s_tick(&cap.timer);assert(buffer[4]==-123);
 writel(0x203,gpio+42*4);a6_policy_vbat_mv=3599;rx_count=1;now+=250000;
 assert(a6_s_tick(&cap.timer)==HRTIMER_NORESTART);
 assert(!cap.ready && readl(gpio+42*4)==0x203 && readl(iis+0x34)==0);
 a6_policy_vbat_mv=4100;
 /* A stop ramp preserves negative polarity and reaches reset within20ms. */
 memset(&s,0,sizeof(s));s.sub=&sub;s.ready=true;s.last_sample=-12000;
 runtime.private_data=&s;assert(!a6_s_trigger(&sub,SNDRV_PCM_TRIGGER_STOP));
 fifo=0;now+=250000;a6_s_tick(&s.timer);assert(last_written<0);
 for(unsigned i=0;i<24 && s.stopping;i++){fifo=0;now+=250000;a6_s_tick(&s.timer);}
 assert(!s.stopping && readl(gpio+42*4)==0x202);
 puts("PASS: actual PCM consumption pointer, signed ramps, capture isolation and watchdog callbacks");
}
'''
declarations = source[source.index('struct a6_s_saved'):source.index('static DEFINE_MUTEX')]
code = prefix + declarations + '\n'.join(function(name) for name in
        ('a6_s_save', 'a6_s_restore_word', 'a6_s_guard', 'a6_s_tick', 'a6_s_watch', 'a6_s_trigger')) + tests
with tempfile.TemporaryDirectory(prefix='a6-alsa-test-') as directory:
    c = Path(directory) / 'test.c'
    binary = Path(directory) / 'test'
    c.write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O2', '-fsanitize=undefined,address',
                    str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

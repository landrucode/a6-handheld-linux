// SPDX-License-Identifier: GPL-2.0-only
/* N42 AP audio: timer-serviced PIO, independent playback/capture lifetimes.
 * All control-bus operations hold a6_touch_lock. No firmware or rail writes. */
#if !IS_ENABLED(CONFIG_HIGH_RES_TIMERS)
#error N42_PIO_audio_requires_high_resolution_timers
#endif
#include <sound/core.h>
#include <sound/pcm.h>
#include <sound/control.h>
#include <linux/workqueue.h>
#include <linux/platform_device.h>
struct a6_s_saved { void __iomem *p; u32 v; };
struct a6_s_stream {
 struct snd_pcm_substream *sub;
 struct hrtimer timer, watchdog;
 struct work_struct fault_work;
 spinlock_t lock;
 struct a6_s_saved saved[64];
 unsigned int saved_count, gates[3], gate_count;
 u32 gate_before[3];
 u8 codec_before[768];
 unsigned int codec_dirty, replay_mismatches, setup_stage;
 u32 failed_codec_reg, mismatch_regs[16];u8 mismatch_want[16],mismatch_got[16];
 u8 clear_before[2],clear_write[2],clear_after[2],clear_final[2];unsigned int clear_attempts;bool clear_io_error;
 snd_pcm_uframes_t pos, period;
 bool ready, running, capture, parent_owned, stopping;
 s16 last_sample, capture_left;bool capture_half;unsigned int stop_frames;
 int error, cleanup, setup_error;
 u64 max_service_gap;
 u64 frames, consumed, last_tick;
};
static DEFINE_MUTEX(a6_s_mutex);
static struct a6_s_stream a6_s_streams[2];
static struct snd_card *a6_s_card;
static struct platform_device *a6_s_device;
static unsigned int a6_s_parent_users;
static u32 a6_s_parent_before;
static unsigned int a6_s_volume;
static bool a6_s_raw_active;

static int a6_s_write(void __iomem *p,u32 v) {writel(v,p);return readl(p)==v ? 0 : -EIO;}
static int a6_s_save(struct a6_s_stream *s,void __iomem *p)
{
 u32 v=readl(p);
 /* All 32 slots enabled is a valid idle mask, not a failed bus read. */
 if((v==U32_MAX && p!=a6_af_mca+0x24 && p!=a6_af_mca+0x38) ||
    v!=readl(p) || s->saved_count>=ARRAY_SIZE(s->saved))return -EBUSY;
 s->saved[s->saved_count++]=(struct a6_s_saved){p,v};return 0;
}
static int a6_s_restore_word(void __iomem *p,u32 v)
{
 writel(v,p);
 /* NCO control acknowledges asynchronously, as in stock clock setup. */
 if(p==a6_af_nco+0x2b0)return a6_af_poll(p,U32_MAX,v);
 return readl(p)==v ? 0 : -EIO;
}
static bool a6_s_guard(void)
{
 return a6_auto_enabled && !a6_auto_fault && !a6_auto_paused && a6_low_enabled && !a6_low_triggered && a6_policy_vbat_mv>=3600 && a6_policy_tbat_c>=10 && a6_policy_tbat_c<=35;
}
static int a6_s_gate(struct a6_s_stream *s,unsigned int off)
{
 u32 v=readl(a6_touch_pmgr+off);unsigned int i=s->gate_count;
 if(i>=3 || v==U32_MAX || ((v&255)!=0 && (v&255)!=255))return -EBUSY;
 s->gates[i]=off;s->gate_before[i]=v;s->gate_count++;
 if(!(v&255)){writel(v|15,a6_touch_pmgr+off);return a6_af_poll(a6_touch_pmgr+off,255,255);}return 0;
}
static int a6_s_parent_get(struct a6_s_stream *s)
{
 int ret;
 if(!a6_s_parent_users){a6_s_parent_before=readl(a6_touch_pmgr+0xa0);if(a6_s_parent_before==U32_MAX || ((a6_s_parent_before&255)!=0 && (a6_s_parent_before&255)!=255))return -EBUSY;
  writel(a6_s_parent_before|15,a6_touch_pmgr+0xa0);ret=a6_af_poll(a6_touch_pmgr+0xa0,255,255);if(ret){writel(a6_s_parent_before,a6_touch_pmgr+0xa0);return ret;}}
 a6_s_parent_users++;s->parent_owned=true;return 0;
}
static int a6_s_amp(u8 reg,u8 value)
{
 u8 rb=0;int ret=a6_at_xfer(0x40,reg,&value,true);
 if(!ret)ret=a6_at_xfer(0x40,reg,&rb,false);
 return ret ? ret : rb==value ? 0 : -EIO;
}
static void a6_s_fault_work(struct work_struct *w)
{
 struct a6_s_stream *s=container_of(w,struct a6_s_stream,fault_work);
 if(s->sub)snd_pcm_stop_xrun(s->sub);
}
static enum hrtimer_restart a6_s_tick(struct hrtimer *timer)
{
 struct a6_s_stream *s=container_of(timer,struct a6_s_stream,timer);
 struct snd_pcm_substream *sub=s->sub;struct snd_pcm_runtime *r=sub->runtime;
 unsigned long flags;unsigned int count=0,n=0;u32 status;bool period=false;u64 now=ktime_get_ns();
 spin_lock_irqsave(&s->lock,flags);
 if(!s->ready)goto stopped;
 if(s->last_tick && now>=s->last_tick && now-s->last_tick>s->max_service_gap)s->max_service_gap=now-s->last_tick;
 if(!a6_s_guard() || (s->running && s->last_tick && now-s->last_tick>2000000)){s->error=-EPIPE;goto fault;}
 s->last_tick=now;
 if(s->capture){
  /* Measured stock IIS0 page: occupancy moves in units of bit13.
   * Pair RX words into mono; the unused slot is near zero. */
  status=readl(a6_ac_iis+0x3c);count=(status>>13)&127;
  if(status==U32_MAX || count>128){s->error=-EIO;goto fault;}
  for(n=0;n<count;n++) {
   u32 sample=readl(a6_ac_iis+0x38);
   if(s->running){
    if(!s->capture_half){s->capture_left=(s16)sample;s->capture_half=true;}
    else {s16 *dst=(s16 *)r->dma_area;int sum=(int)s->capture_left+(int)(s16)sample;
     if(sum>32767)sum=32767;else if(sum<-32768)sum=-32768;
     dst[s->pos]=(s16)sum;
     s->capture_half=false;s->pos=(s->pos+1)%r->buffer_size;s->frames++;s->period++;}
   }
  }
 }else{
  status=readl(a6_af_mca+0x40);count=status&255;
  if(status==U32_MAX || count>128 || (status&0x2000) || (s->running && (status&0x1000))){s->error=-EPIPE;goto fault;}
  if(s->running){
   u64 consumed=s->frames>count ? s->frames-count : 0;
   consumed=min(consumed,s->frames);
   s->period+=consumed-s->consumed;s->consumed=consumed;u32 pos;div_u64_rem(consumed,r->buffer_size,&pos);s->pos=pos;
  }
  if(count<64)for(n=count;n<96;n++) {
   s16 sample=0;u32 sample_index;
   if(s->stopping){sample=(int)s->last_sample*(960-(int)s->stop_frames)/960;if(++s->stop_frames>=960){writel(0x202,a6_touch_gpio+42*4);s->stopping=false;s->last_sample=0;}}
   else if(s->running){
    u64 queued_rem;
    div64_u64_rem(s->frames,r->boundary,&queued_rem);
    snd_pcm_uframes_t queued=queued_rem;
    snd_pcm_uframes_t available=(READ_ONCE(r->control->appl_ptr)+r->boundary-queued)%r->boundary;
    if(!available || available>r->buffer_size)break;
    div_u64_rem(s->frames,r->buffer_size,&sample_index);sample=((s16 *)r->dma_area)[sample_index];s->frames++;
    if(s->frames<960)sample=(int)sample*(int)s->frames/960;}
   if(s->running)s->last_sample=sample;
   writew((u16)sample,a6_af_mca+0x28);
  }
  /* Stock alive timer,20ms. No I2C in timer context. */
  if(a6_at_alive_active && now-a6_at_alive_time>=20000000){a6_at_alive[1]^=1;writel(a6_at_alive[1],a6_touch_gpio+9*4);a6_at_alive_time=now;}
 }
 if(s->running && s->period>=r->period_size){s->period%=r->period_size;period=true;}
 spin_unlock_irqrestore(&s->lock,flags);
 if(period)snd_pcm_period_elapsed(sub);
 hrtimer_forward_now(timer,ns_to_ktime(250000));return HRTIMER_RESTART;
fault:
 s->ready=false;s->running=false;
 if(!s->capture)writel(0x202,a6_touch_gpio+42*4);
 else writel(0,a6_ac_iis+0x34);
 schedule_work(&s->fault_work);
stopped:
 spin_unlock_irqrestore(&s->lock,flags);return HRTIMER_NORESTART;
}
/* Separate deadline timer: a stalled FIFO service must reset the amplifier. */
static enum hrtimer_restart a6_s_watch(struct hrtimer *timer)
{
 struct a6_s_stream *s=container_of(timer,struct a6_s_stream,watchdog);
 unsigned long flags;bool fault=false;u64 now=ktime_get_ns();
 spin_lock_irqsave(&s->lock,flags);
 if(!s->ready){spin_unlock_irqrestore(&s->lock,flags);return HRTIMER_NORESTART;}
 if(!a6_s_guard() || (s->last_tick && now-s->last_tick>1750000)){
  writel(0x202,a6_touch_gpio+42*4);s->ready=s->running=false;s->error=-ETIMEDOUT;fault=true;
 }
 spin_unlock_irqrestore(&s->lock,flags);
 if(fault){schedule_work(&s->fault_work);return HRTIMER_NORESTART;}
 hrtimer_forward_now(timer,ns_to_ktime(1000000));return HRTIMER_RESTART;
}
static int a6_s_codec_clear_probe(struct a6_s_stream *s,u32 reg,u8 expected,u8 observed)
{
 unsigned int slot;u8 mask,reply[5]={0};int ret,undo;
 if(!a6_s_raw_active)return -EUCLEAN;
 if(reg==0x4a){slot=0;mask=0x80;}else if(reg==0x4f){slot=1;mask=1;}else return -EUCLEAN;
 /* Only test the exact extra bit observed after restoring the preimage.
  * Rewrite its current byte, then restore the expected byte again. */
 if((expected&mask) || (observed^expected)!=mask)return -EUCLEAN;
 s->clear_attempts|=1U<<slot;s->clear_before[slot]=observed;s->clear_write[slot]=observed;
 ret=a6_ac_transfer(reg,reply,true,observed);
 if(!ret)ret=a6_ac_read_reg(reg,reply);
 if(!ret)s->clear_after[slot]=reply[4];
 undo=a6_ac_transfer(reg,reply,true,expected);
 if(!undo)undo=a6_ac_read_reg(reg,reply);
 if(!undo)s->clear_final[slot]=reply[4];
 if(ret || undo){s->clear_io_error=true;return -EUCLEAN;}
 /* The final exact readback decides restoration; the intermediate byte
  * records whether the observed behaviour supports the W1C hypothesis. */
 return s->clear_final[slot]==expected ? 0 : -EUCLEAN;
}
static int a6_s_codec_restore(struct a6_s_stream *s)
{
 unsigned int i;int cr=0;
 /* Complete control restoration and settling before probing the two bits. */
 for(i=s->codec_dirty;i-->0;){u8 rb[5];if(a6_ac_transfer(a6_mic_codec_regs[i],rb,true,s->codec_before[i]))cr=-EUCLEAN;}
 {u64 deadline=ktime_get_ns()+50000000;
  for(i=0;i<s->codec_dirty;i++){
   u8 rb[5]={0};int ret;
   do {
    ret=a6_ac_read_reg(a6_mic_codec_regs[i],rb);
    if(ret || rb[4]==s->codec_before[i])break;
    if(ktime_get_ns()>=deadline)break;
    usleep_range(1000,1500);
   }while(ktime_get_ns()<deadline);
   if(ret)cr=-EUCLEAN;
  }
 }
 if(a6_s_raw_active){
  static const u32 regs[]={0x4f,0x4a};unsigned int slot;
  for(slot=0;slot<ARRAY_SIZE(regs);slot++)for(i=0;i<s->codec_dirty;i++)if(a6_mic_codec_regs[i]==regs[slot]){
   u8 rb[5]={0};int ret=a6_ac_read_reg(regs[slot],rb);
   if(ret)cr=-EUCLEAN;
   else if(rb[4]!=s->codec_before[i])a6_s_codec_clear_probe(s,regs[slot],s->codec_before[i],rb[4]);
   break;
  }
  if(s->clear_io_error)cr=-EUCLEAN;
 }
 /* Recheck the whole bank after all probes: one flag may affect another. */
 for(i=0;i<s->codec_dirty;i++){
  u8 rb[5]={0};int ret=a6_ac_read_reg(a6_mic_codec_regs[i],rb);
  if(ret || rb[4]!=s->codec_before[i]){pr_err("a6-alsa: final codec restore reg=%x expected=%02x observed=%02x error=%d\n",a6_mic_codec_regs[i],s->codec_before[i],rb[4],ret);cr=-EUCLEAN;}
 }
 s->codec_dirty=0;return cr;
}
static int a6_s_restore(struct a6_s_stream *s)
{
 unsigned int i;int cr=0;
 /* A second close with no owned resources must not erase a restore failure. */
 if(s->cleanup && !s->saved_count && !s->gate_count && !s->parent_owned && !s->codec_dirty)return s->cleanup;
 if(!s->capture && s->saved_count){
  writel(0x202,a6_touch_gpio+42*4);a6_at_alive_active=false;
  writel(0x301,a6_af_mca+0x44);if(a6_af_poll(a6_af_mca+0x44,U32_MAX,0))cr=-EUCLEAN;
  writel(readl(a6_af_mca+0x40)&0x30003000,a6_af_mca+0x40);
 }
 else if(s->codec_dirty){
  writel(0,a6_ac_iis+0x34);
  if(a6_s_codec_restore(s))cr=-EUCLEAN;
 }
 for(i=s->saved_count;i-->0;)if(a6_s_restore_word(s->saved[i].p,s->saved[i].v)){pr_err("a6-alsa: MMIO restore index=%u expected=%08x observed=%08x\n",i,s->saved[i].v,readl(s->saved[i].p));cr=-EUCLEAN;}
 s->saved_count=0;
 for(i=s->gate_count;i-->0;){writel(s->gate_before[i],a6_touch_pmgr+s->gates[i]);if(a6_af_poll(a6_touch_pmgr+s->gates[i],U32_MAX,s->gate_before[i]))cr=-EUCLEAN;}
 s->gate_count=0;
 if(s->parent_owned){s->parent_owned=false;if(!--a6_s_parent_users){writel(a6_s_parent_before,a6_touch_pmgr+0xa0);if(a6_af_poll(a6_touch_pmgr+0xa0,U32_MAX,a6_s_parent_before))cr=-EUCLEAN;}}
 s->cleanup=cr;return cr;
}
static int a6_s_play_setup(struct a6_s_stream *s)
{
 static const u32 cfg[]={0x1010,0x0f107000,1,0,0x108,0xd,0x00170004,1,0x10a,0xd,0x002f0004,3};
 unsigned int i;u8 id=0;int ret;
 if(a6_memory_capture_copy[512]!=0x53504431 || a6_memory_capture_copy[514]!=1 ||
    (a6_memory_capture_copy[513]&0x31)!=1 || a6_memory_capture_copy[515]!=20 ||
    a6_memory_capture_copy[483]!=24000000)return -ENODATA;
 for(i=0;i<20;i++)if(i!=12 && i!=16 && i!=19 && ((u8 *)a6_memory_capture_copy)[0x820+i]!=a6_at_config[i])return -ENODATA;
 if((a6_memory_capture_copy[513]&4) && a6_memory_capture_copy[517]!=20)return -EINVAL;
 #define S_SAVE(p) do{ret=a6_s_save(s,p);if(ret)return ret;}while(0)
 #define S_WRITE(p,v) do{ret=a6_s_write(p,v);if(ret)return ret;}while(0)
 ret=a6_s_gate(s,0xe0);if(ret)return ret;ret=a6_s_gate(s,0xac);if(ret)return ret;
 for(i=0;i<ARRAY_SIZE(a6_af_offsets);i++)S_SAVE(a6_af_mca+a6_af_offsets[i]);
 S_SAVE(a6_af_acs+0x24);S_SAVE(a6_af_acs+0x18);
 S_SAVE(a6_ai_switch+8);S_SAVE(a6_ai_switch+0x24);S_SAVE(a6_ai_switch+0x48);
 S_SAVE(a6_touch_gpio+42*4);S_SAVE(a6_touch_gpio+9*4);
 S_SAVE(a6_touch_gpio+90*4);S_SAVE(a6_touch_gpio+91*4);
 S_SAVE(a6_ai_iis);S_SAVE(a6_ai_iis+8);S_SAVE(a6_ai_iis+0x34);
 if(readl(a6_touch_gpio+42*4)!=0x202 || (readl(a6_ai_switch+8)&0xf01f) || (readl(a6_ai_switch+0x24)&0xf0f))return -EBUSY;
 S_WRITE(a6_touch_gpio+90*4,0x202);S_WRITE(a6_touch_gpio+91*4,0x202);msleep(50);
 S_WRITE(a6_af_acs+0x24,0);S_WRITE(a6_af_acs+0x18,0);
 writel(0x301,a6_af_mca+0x44);ret=a6_af_poll(a6_af_mca+0x44,U32_MAX,0);if(ret)return ret;
 for(i=0;i<ARRAY_SIZE(cfg);i++)S_WRITE(a6_af_mca+a6_af_offsets[i],cfg[i]);
 S_WRITE(a6_ai_iis+8,0);S_WRITE(a6_ai_iis+0x34,0);
 writel(0x134,a6_ai_iis);ret=a6_af_poll(a6_ai_iis,U32_MAX,0x136);if(ret)return ret;
 S_WRITE(a6_ai_switch+0x48,readl(a6_ai_switch+0x48)|1);
 S_WRITE(a6_ai_switch+8,0xf000);S_WRITE(a6_ai_switch+0x24,2);
 for(i=0;i<96;i++)writew(0,a6_af_mca+0x28);
 S_WRITE(a6_af_mca+24,0x109);S_WRITE(a6_af_mca+12,0x0f107002);
 s->last_tick=ktime_get_ns();s->ready=true;
 hrtimer_start(&s->timer,ns_to_ktime(250000),HRTIMER_MODE_REL);
 hrtimer_start(&s->watchdog,ns_to_ktime(1000000),HRTIMER_MODE_REL);
 msleep(10);S_WRITE(a6_touch_gpio+42*4,0x203);usleep_range(1000,2000);
 ret=a6_at_xfer(0x40,5,&id,false);if(ret || id!=0xb0)return ret ? ret : -ENODEV;
 a6_at_stock44100=true;a6_at_variant=4;a6_at_feeding=false;atomic_set(&a6_at_expired,0);
 a6_at_alive[1]=readl(a6_touch_gpio+9*4);a6_at_alive_time=ktime_get_ns();
 for(i=0;i<A6_AT_STOCK44100_MASTER_SHUTDOWN;i++){ret=a6_at_op(i);if(ret)return ret;}
 ret=a6_s_amp(7,0xf8);if(ret)return ret;ret=a6_s_amp(8,0x49);if(ret)return ret;ret=a6_s_amp(0x10,a6_s_volume);if(ret)return ret;
 return a6_s_guard() ? 0 : -ERANGE;
}
/* Only discrepancies observed in the successful full-bank hardware runs.
 * Keep unexpected values fatal for PCM and retain every readback in status. */
static bool a6_s_codec_observed(u32 reg,u8 want,u8 got)
{
 return (reg==0x4a && want==0x87 && got==0x07) ||
        (reg==0x4b && want==0x00 && got==0x80) ||
        (reg==0x75 && want==0x00 && got==0x60) ||
        (reg==0x544 && want==0x44 && (got==0x54 || got==0x45));
}
static int a6_s_codec_replay(struct a6_s_stream *s)
{
 unsigned int i;int ret;u8 reply[5];
 for(i=0;i<ARRAY_SIZE(a6_mic_codec_regs);i++){
  s->codec_dirty=i+1;s->failed_codec_reg=a6_mic_codec_regs[i];
  ret=a6_ac_transfer(a6_mic_codec_regs[i],reply,true,a6_mic_codec_values[i]);if(ret)return ret;
  ret=a6_ac_read_reg(a6_mic_codec_regs[i],reply);if(ret)return ret;
  if(reply[4]!=a6_mic_codec_values[i]){
   unsigned int n=s->replay_mismatches++;
   if(n<ARRAY_SIZE(s->mismatch_regs)){s->mismatch_regs[n]=a6_mic_codec_regs[i];s->mismatch_want[n]=a6_mic_codec_values[i];s->mismatch_got[n]=reply[4];}
   /* Captured banks also contain values that need not latch on write.
    * Preserve every discrepancy; PCM continues only for observed successful values. */
   if(!a6_s_raw_active && !a6_s_codec_observed(a6_mic_codec_regs[i],a6_mic_codec_values[i],reply[4]))return -EIO;
  }
 }
 s->failed_codec_reg=0;return 0;
}
static int a6_s_capture_setup(struct a6_s_stream *s)
{
 unsigned int i;int ret;u8 reply[5];
 s->setup_stage=1;s->replay_mismatches=0;s->failed_codec_reg=0;
 if(a6_memory_capture_copy[0]!=0x41364d31 || a6_memory_capture_copy[1]!=1 ||
    a6_memory_capture_copy[0x600/4+324-256]!=342000000 || a6_memory_capture_copy[483]!=24000000)return -ENODATA;
 s->setup_stage=2;ret=a6_s_gate(s,0xa4);if(ret)return ret;ret=a6_s_gate(s,0xf0);if(ret)return ret;
 for(i=0;i<ARRAY_SIZE(a6_ac_spi_offsets);i++){S_SAVE(a6_ac_spi+a6_ac_spi_offsets[i]);a6_ac_spi_before[i]=readl(a6_ac_spi+a6_ac_spi_offsets[i]);}
 S_SAVE(a6_touch_gpio+87*4);S_SAVE(a6_ai_switch);S_SAVE(a6_ai_switch+0x40);S_SAVE(a6_af_acs+0x10);
 {static const u32 offs[]={0,4,8,0x30,0x34,0x40};for(i=0;i<ARRAY_SIZE(offs);i++)S_SAVE(a6_ac_iis+offs[i]);}
 for(i=0;i<3;i++)S_SAVE(a6_af_nco+0x2b0+4*i);
 if(readl(a6_ac_spi) || readl(a6_ac_spi+8) || readl(a6_ac_spi+0x34) || readl(a6_ac_spi+0x4c) ||
    (readl(a6_ac_iis+8)&6) || (readl(a6_ac_iis+0x34)&6) || (readl(a6_af_nco+0x2b0)&0x40000002))return -EBUSY;
 s->setup_stage=3;S_WRITE(a6_af_acs+0x10,0);
 /* Captured NCOf0 pair generates1.4112MHz;44.1k stereo16. */
 {static const u32 nc[][2]={{0,0x82000000},{0,0x92000000},{4,0x002b1100},{8,0xebc88f80},{0,0x92000400},{0,0x92000c00},{0,0x92000800}};
 for(i=0;i<ARRAY_SIZE(nc);i++){writel(nc[i][1],a6_af_nco+0x2b0+nc[i][0]);ret=a6_af_poll(a6_af_nco+0x2b0,0x40000002,0);if(ret)return ret;
  if(readl(a6_af_nco+0x2b0+nc[i][0])!=nc[i][1])return -EIO;}}
 s->setup_stage=4;S_WRITE(a6_ac_iis+8,0);S_WRITE(a6_ac_iis+0x34,0);S_WRITE(a6_ac_iis+4,0x03000081);S_WRITE(a6_ac_iis+0x30,0x1000);S_WRITE(a6_ac_iis+0x40,0);
 S_WRITE(a6_ai_switch,0x9010);S_WRITE(a6_ai_switch+0x40,readl(a6_ai_switch+0x40)|1);
 S_WRITE(a6_ac_iis,0x101);
 s->setup_stage=5;ret=a6_ac_read_reg(5,reply);if(ret || reply[4]!=0xb1)return ret ? ret : -ENODEV;
 for(i=0;i<ARRAY_SIZE(a6_mic_codec_regs);i++){s->failed_codec_reg=a6_mic_codec_regs[i];ret=a6_ac_read_reg(a6_mic_codec_regs[i],reply);if(ret)return ret;s->codec_before[i]=reply[4];}
 s->setup_stage=6;ret=a6_s_codec_replay(s);if(ret)return ret;
 s->setup_stage=7;
 S_WRITE(a6_ac_iis+0x34,0x01feca06);
 s->ready=true;if(!a6_s_raw_active)hrtimer_start(&s->timer,ns_to_ktime(250000),HRTIMER_MODE_REL);return 0;
 #undef S_SAVE
 #undef S_WRITE
}
static const struct snd_pcm_hardware a6_s_hw={
 .info=SNDRV_PCM_INFO_MMAP|SNDRV_PCM_INFO_MMAP_VALID|SNDRV_PCM_INFO_INTERLEAVED|SNDRV_PCM_INFO_BLOCK_TRANSFER,
 .formats=SNDRV_PCM_FMTBIT_S16_LE,.rates=SNDRV_PCM_RATE_48000,.rate_min=48000,.rate_max=48000,
 .channels_min=1,.channels_max=1,.buffer_bytes_max=65536,.period_bytes_min=256,.period_bytes_max=16384,.periods_min=2,.periods_max=32,
};
static int a6_s_open(struct snd_pcm_substream *sub)
{
 struct a6_s_stream *s=&a6_s_streams[sub->stream];sub->runtime->private_data=s;s->sub=sub;s->capture=sub->stream==SNDRV_PCM_STREAM_CAPTURE;
 sub->runtime->hw=a6_s_hw;if(s->capture){sub->runtime->hw.rates=SNDRV_PCM_RATE_44100;sub->runtime->hw.rate_min=sub->runtime->hw.rate_max=44100;sub->runtime->hw.channels_min=sub->runtime->hw.channels_max=1;}
 return snd_pcm_hw_constraint_integer(sub->runtime,SNDRV_PCM_HW_PARAM_PERIODS);
}
static int a6_s_hw_free(struct snd_pcm_substream *sub)
{
 struct a6_s_stream *s=sub->runtime->private_data;int ret;
 if(!s->capture && READ_ONCE(s->stopping))msleep(21);
 WRITE_ONCE(s->ready,false);hrtimer_cancel(&s->timer);hrtimer_cancel(&s->watchdog);cancel_work_sync(&s->fault_work);
 s->running=false;
 mutex_lock(&a6_s_mutex);mutex_lock(&a6_touch_lock);ret=a6_s_restore(s);mutex_unlock(&a6_touch_lock);mutex_unlock(&a6_s_mutex);return ret;
}
static int a6_s_close(struct snd_pcm_substream *sub)
{
 struct a6_s_stream *s=sub->runtime->private_data;int ret=a6_s_hw_free(sub);
 s->sub=NULL;return ret;
}
static int a6_s_prepare(struct snd_pcm_substream *sub)
{
 struct a6_s_stream *s=sub->runtime->private_data;int ret;
 WRITE_ONCE(s->ready,false);hrtimer_cancel(&s->timer);hrtimer_cancel(&s->watchdog);cancel_work_sync(&s->fault_work);
 mutex_lock(&a6_s_mutex);mutex_lock(&a6_touch_lock);
 if(s->cleanup){ret=-EUCLEAN;goto out;}
 ret=a6_s_restore(s);if(ret)goto out;
 s->capture_half=false;s->capture_left=0;
 s->pos=s->period=0;s->frames=s->consumed=s->last_tick=0;s->running=s->stopping=false;s->stop_frames=0;s->last_sample=0;s->error=0;
 if(!hrtimer_highres_enabled() || READ_ONCE(hrtimer_resolution)>250000){ret=-EOPNOTSUPP;goto out;}
 if(!a6_s_guard()){ret=-EBUSY;goto out;}
 ret=a6_s_parent_get(s);if(!ret)ret=s->capture ? a6_s_capture_setup(s) : a6_s_play_setup(s);
 if(!ret && s->capture){
  /* Drain startup samples without holding the charger's control-bus lock. */
  mutex_unlock(&a6_touch_lock);msleep(150);mutex_lock(&a6_touch_lock);
  if(s->error || !s->ready || !a6_s_guard())ret=s->error ? s->error : -EIO;
 }
 if(ret){WRITE_ONCE(s->ready,false);hrtimer_cancel(&s->timer);hrtimer_cancel(&s->watchdog);a6_s_restore(s);}
out:
 s->setup_error=ret;
 mutex_unlock(&a6_touch_lock);mutex_unlock(&a6_s_mutex);return ret;
}
static int a6_s_trigger(struct snd_pcm_substream *sub,int cmd)
{
 struct a6_s_stream *s=sub->runtime->private_data;unsigned long flags;int ret=0;
 spin_lock_irqsave(&s->lock,flags);
 if(cmd==SNDRV_PCM_TRIGGER_START){if(!s->ready || s->error)ret=-EIO;else{if(!s->capture){writel(readl(a6_af_mca+0x40)&0x1000,a6_af_mca+0x40);}s->running=true;s->frames=s->consumed=0;s->last_tick=ktime_get_ns();}}
 else if(cmd==SNDRV_PCM_TRIGGER_STOP){s->running=false;if(!s->capture){s->stopping=true;s->stop_frames=0;}}
 else ret=-EINVAL;
 spin_unlock_irqrestore(&s->lock,flags);return ret;
}
static snd_pcm_uframes_t a6_s_pointer(struct snd_pcm_substream *sub)
{
 struct a6_s_stream *s=sub->runtime->private_data;return READ_ONCE(s->pos);
}
static const struct snd_pcm_ops a6_s_ops={.open=a6_s_open,.close=a6_s_close,.hw_free=a6_s_hw_free,.prepare=a6_s_prepare,.trigger=a6_s_trigger,.pointer=a6_s_pointer};
static int a6_s_volume_info(struct snd_kcontrol *k,struct snd_ctl_elem_info *v)
{v->type=SNDRV_CTL_ELEM_TYPE_INTEGER;v->count=1;v->value.integer.min=0;v->value.integer.max=52;return 0;}
static int a6_s_volume_get(struct snd_kcontrol *k,struct snd_ctl_elem_value *v)
{v->value.integer.value[0]=READ_ONCE(a6_s_volume);return 0;}
static int a6_s_volume_put(struct snd_kcontrol *k,struct snd_ctl_elem_value *v)
{
 long value=v->value.integer.value[0];int ret=0;bool changed;
 if(value<0 || value>52)return -EINVAL;
 mutex_lock(&a6_s_mutex);mutex_lock(&a6_touch_lock);changed=value!=a6_s_volume;
 if(changed && a6_s_streams[0].ready)ret=a6_s_amp(0x10,value);
 if(!ret)a6_s_volume=value;
 mutex_unlock(&a6_touch_lock);mutex_unlock(&a6_s_mutex);return ret ? ret : changed;
}
static ssize_t a6_s_status(struct kobject *k,struct kobj_attribute *a,char *buf)
{
 unsigned int i;ssize_t n=0;
 mutex_lock(&a6_s_mutex);
 n+=sysfs_emit_at(buf,n,"A6_ALSA_V1 parent_users=%u volume_reg10=%u\n",a6_s_parent_users,a6_s_volume);
 for(i=0;i<2;i++){
  struct a6_s_stream *s=&a6_s_streams[i];unsigned long flags;
  spin_lock_irqsave(&s->lock,flags);
  n+=sysfs_emit_at(buf,n,"stream=%s ready=%u running=%u error=%d cleanup=%d queued=%llu consumed=%llu pointer=%lu status=%08x setup_error=%d max_service_gap_us=%llu timer_resolution_ns=%u\n",
   i ? "capture" : "playback",s->ready,s->running,s->error,s->cleanup,s->frames,s->consumed,s->pos,
   s->ready ? readl(i ? a6_ac_iis+0x3c : a6_af_mca+0x40) : 0,s->setup_error,div_u64(s->max_service_gap,1000),READ_ONCE(hrtimer_resolution));
  spin_unlock_irqrestore(&s->lock,flags);
 }
 mutex_unlock(&a6_s_mutex);return n;
}
static struct kobj_attribute a6_s_status_attr=__ATTR(a6_alsa_status,0400,a6_s_status,NULL);

#ifdef A6_AUDIO_RAW_CAPTURE
/* Headless, bounded raw acquisition. No PCM conversion or desktop dependency. */
struct a6_raw_result {
 u64 elapsed, words, nonzero, collect_after;
 u32 first_status, last_status, before[8], after[8], raw[64], startup[16];
 unsigned int samples, startup_samples, probes, setup_stage, mismatches;
 u32 failed_reg,mismatch_regs[16];u8 mismatch_want[16],mismatch_got[16];
 int error, cleanup;
};
static struct a6_raw_result a6_raw_results[2];
static int a6_raw_burst(struct a6_raw_result *r,unsigned int off)
{
 u32 status=readl(a6_ac_iis+off+0x3c);unsigned int count=(status>>13)&127,n;
 if(status==U32_MAX)return -EIO;
 count=min(count,32U);
 for(n=0;n<count;n++){
  u32 word=readl(a6_ac_iis+off+0x38);
  if(ktime_get_ns()<r->collect_after)continue;
  if(r->startup_samples<ARRAY_SIZE(r->startup))r->startup[r->startup_samples++]=word;
  /* Keep an unconverted window beginning with the first nonzero word. */
  if((word || r->nonzero) && r->samples<ARRAY_SIZE(r->raw))r->raw[r->samples++]=word;
  r->words++;if(word)r->nonzero++;
 }
 if(count && r->probes<ARRAY_SIZE(r->before)){
  r->before[r->probes]=status;r->after[r->probes++]=readl(a6_ac_iis+off+0x3c);
 }
 return 0;
}

static ssize_t a6_raw_run(struct kobject *k,struct kobj_attribute *a,const char *buf,size_t len)
{
 struct a6_s_stream *s=&a6_s_streams[1];unsigned int bank;int ret=0;
 if(!sysfs_streq(buf,"recording-banks-raw-restore"))return -EINVAL;
 mutex_lock(&a6_s_mutex);
 if(a6_s_streams[0].sub || s->sub || a6_s_parent_users || s->cleanup){ret=-EBUSY;goto out;}
 memset(a6_raw_results,0,sizeof(a6_raw_results));
 a6_s_raw_active=true;s->capture=true;s->clear_attempts=0;s->clear_io_error=false;
 memset(s->clear_before,0,sizeof(s->clear_before));memset(s->clear_write,0,sizeof(s->clear_write));memset(s->clear_after,0,sizeof(s->clear_after));memset(s->clear_final,0,sizeof(s->clear_final));
 /* Both ports are read under one unchanged configuration and one lifetime. */
 mutex_lock(&a6_touch_lock);
 if(!a6_s_guard())ret=-EBUSY;
 else {ret=a6_s_parent_get(s);if(!ret)ret=a6_s_capture_setup(s);}
 mutex_unlock(&a6_touch_lock);
 for(bank=0;bank<2;bank++){
  struct a6_raw_result *r=&a6_raw_results[bank];u64 start;u32 off=bank*0x80;
  if(!ret){
   start=ktime_get_ns();r->collect_after=bank ? start : start+150000000;r->first_status=readl(a6_ac_iis+off+0x3c);
   do {
    if(!a6_s_guard()){ret=-ECANCELED;break;}
    ret=a6_raw_burst(r,off);if(ret)break;
    udelay(250);cond_resched();
   }while(ktime_get_ns()<r->collect_after || ktime_get_ns()-r->collect_after<250000000);
   r->elapsed=ktime_get_ns()>=r->collect_after ? ktime_get_ns()-r->collect_after : 0;r->last_status=readl(a6_ac_iis+off+0x3c);
  }
  r->setup_stage=s->setup_stage;r->failed_reg=s->failed_codec_reg;r->mismatches=s->replay_mismatches;
  memcpy(r->mismatch_regs,s->mismatch_regs,sizeof(r->mismatch_regs));memcpy(r->mismatch_want,s->mismatch_want,sizeof(r->mismatch_want));memcpy(r->mismatch_got,s->mismatch_got,sizeof(r->mismatch_got));
  r->error=ret;
  if(ret)break;
 }
 s->ready=false;
 mutex_lock(&a6_touch_lock);
 {int cleanup=a6_s_restore(s);
  for(bank=0;bank<2;bank++)a6_raw_results[bank].cleanup=cleanup;
  if(!ret)ret=cleanup;
 }
 mutex_unlock(&a6_touch_lock);
 a6_s_raw_active=false;
out:
 mutex_unlock(&a6_s_mutex);return ret ? ret : len;
}
static ssize_t a6_raw_status(struct kobject *k,struct kobj_attribute *a,char *buf)
{
 unsigned int bank,i;ssize_t n=0;
 mutex_lock(&a6_s_mutex);
 {struct a6_s_stream *s=&a6_s_streams[1];
  n+=sysfs_emit_at(buf,n,"clear_attempts=%u clear_io_error=%u reg4a=%02x/%02x/%02x/%02x reg4f=%02x/%02x/%02x/%02x\n",s->clear_attempts,s->clear_io_error,s->clear_before[0],s->clear_write[0],s->clear_after[0],s->clear_final[0],s->clear_before[1],s->clear_write[1],s->clear_after[1],s->clear_final[1]);
 }
 for(bank=0;bank<2;bank++){
  struct a6_raw_result *r=&a6_raw_results[bank];
  n+=sysfs_emit_at(buf,n,"bank=%02x error=%d cleanup=%d elapsed_ns=%llu words=%llu nonzero=%llu status=%08x/%08x\n",bank*0x80,r->error,r->cleanup,r->elapsed,r->words,r->nonzero,r->first_status,r->last_status);
  n+=sysfs_emit_at(buf,n,"setup_stage=%u failed_reg=%04x readback_mismatches=%u\n",r->setup_stage,r->failed_reg,r->mismatches);
  for(i=0;i<min(r->mismatches,16U);i++)n+=sysfs_emit_at(buf,n,"mismatch=%04x:%02x/%02x\n",r->mismatch_regs[i],r->mismatch_want[i],r->mismatch_got[i]);
  for(i=0;i<r->probes;i++)n+=sysfs_emit_at(buf,n,"probe=%u:%u %08x>%08x\n",bank,i,r->before[i],r->after[i]);
  n+=sysfs_emit_at(buf,n,"startup%u=",bank);
  for(i=0;i<r->startup_samples;i++)n+=sysfs_emit_at(buf,n,"%08x%c",r->startup[i],i+1==r->startup_samples ? '\n' : ',');
  if(!r->startup_samples)n+=sysfs_emit_at(buf,n,"\n");
  n+=sysfs_emit_at(buf,n,"raw%u=",bank);if(!r->samples)n+=sysfs_emit_at(buf,n,"\n");
  for(i=0;i<r->samples;i++)n+=sysfs_emit_at(buf,n,"%08x%c",r->raw[i],i+1==r->samples ? '\n' : ',');
 }
 mutex_unlock(&a6_s_mutex);return n;
}
static struct kobj_attribute a6_raw_run_attr=__ATTR(a6_capture_raw_run,0200,NULL,a6_raw_run);
static struct kobj_attribute a6_raw_status_attr=__ATTR(a6_capture_raw_status,0400,a6_raw_status,NULL);
#endif

static int __init a6_s_init(void)
{
 struct snd_pcm *pcm;int ret;unsigned int i;
 const struct snd_kcontrol_new volume={.iface=SNDRV_CTL_ELEM_IFACE_MIXER,.name="Speaker Playback Volume",.info=a6_s_volume_info,.get=a6_s_volume_get,.put=a6_s_volume_put};
 if(!a6_af_mca || !a6_ac_spi || !a6_ac_iis)return -ENODEV;
 a6_s_device=platform_device_register_simple("a6-audio",-1,NULL,0);if(IS_ERR(a6_s_device))return PTR_ERR(a6_s_device);
 ret=snd_card_new(&a6_s_device->dev,-1,"N42",THIS_MODULE,0,&a6_s_card);if(ret)goto fail;
 strscpy(a6_s_card->driver,"N42PIO");strscpy(a6_s_card->shortname,"N42 Audio");strscpy(a6_s_card->longname,"N42 MCA0 speaker and IIS0 microphone");
 for(i=0;i<2;i++){spin_lock_init(&a6_s_streams[i].lock);INIT_WORK(&a6_s_streams[i].fault_work,a6_s_fault_work);hrtimer_setup(&a6_s_streams[i].timer,a6_s_tick,CLOCK_MONOTONIC,HRTIMER_MODE_REL);hrtimer_setup(&a6_s_streams[i].watchdog,a6_s_watch,CLOCK_MONOTONIC,HRTIMER_MODE_REL);}
 ret=snd_pcm_new(a6_s_card,"N42",0,1,1,&pcm);if(ret)goto fail;
 snd_pcm_set_ops(pcm,SNDRV_PCM_STREAM_PLAYBACK,&a6_s_ops);snd_pcm_set_ops(pcm,SNDRV_PCM_STREAM_CAPTURE,&a6_s_ops);
 ret=snd_pcm_set_managed_buffer_all(pcm,SNDRV_DMA_TYPE_VMALLOC,NULL,65536,65536);if(ret)goto fail;
 ret=snd_ctl_add(a6_s_card,snd_ctl_new1(&volume,NULL));if(ret)goto fail;
 ret=sysfs_create_file(firmware_kobj,&a6_s_status_attr.attr);if(ret)goto fail;
 #ifdef A6_AUDIO_RAW_CAPTURE
 ret=sysfs_create_file(firmware_kobj,&a6_raw_run_attr.attr);if(ret)goto remove_status;
 ret=sysfs_create_file(firmware_kobj,&a6_raw_status_attr.attr);if(ret){sysfs_remove_file(firmware_kobj,&a6_raw_run_attr.attr);goto remove_status;}
#endif
 ret=snd_card_register(a6_s_card);if(!ret)return 0;
#ifdef A6_AUDIO_RAW_CAPTURE
 sysfs_remove_file(firmware_kobj,&a6_raw_run_attr.attr);sysfs_remove_file(firmware_kobj,&a6_raw_status_attr.attr);
remove_status:
#endif
 sysfs_remove_file(firmware_kobj,&a6_s_status_attr.attr);
fail:
 snd_card_free(a6_s_card);platform_device_unregister(a6_s_device);return ret;
}
late_initcall(a6_s_init);

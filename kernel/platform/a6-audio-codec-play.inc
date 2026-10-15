// SPDX-License-Identifier: GPL-2.0-only
/* Called only with the charger lock held and layout0 MCA0 configured.
 * Codec VSP RX slot2 is the first reference input (DT RX maskfc).
 * Eight slots, only slot2 nonzero; no amp enable. */
static u8 a6_ac_saved[128],a6_ac_restored[128],a6_ac_dirty[128];
static u32 a6_ac_log[384][6],a6_ac_route[2][3];
static unsigned int a6_ac_log_count,a6_ac_preimages,a6_ac_slot,a6_ac_peak_level;
static bool a6_at_reference,a6_ac_play_attempted,a6_ac_output_enabled;
static unsigned int a6_ac_drain_rate;
static u8 a6_ac_reference_state[4];
static int a6_ac_feed(void)
{
 u32 s;unsigned int n;int sample;
 if(!a6_at_feeding)return 0;
 if(atomic_read(&a6_at_expired))return -ETIMEDOUT;
 s=readl(a6_af_mca+0x40);
 if(s==U32_MAX || (s&255)>128 || (s&0x2000))return -EIO;
 if(a6_at_wave && (s&0x1000))return -EPIPE;
 if((s&255)>a6_ac_peak_level)a6_ac_peak_level=s&255;
 if((s&255)>=64)return 0;
 for(n=s&255;n<96;n++) {
  sample=0;
  if(a6_at_wave && a6_ac_slot==2 && a6_at_samples<48000) {
   unsigned int elapsed=div_u64(ktime_get_ns()-a6_at_wave_start,1000);
   unsigned int ramp=elapsed<500000 ? elapsed : (elapsed<1000000 ? 1000000-elapsed : 0);
   sample=(int)a6_at_peak*a6_at_sine[a6_at_samples%48]/8;
   if(ramp<20000)sample=sample*(int)ramp/20000;
   a6_at_samples++;
  }
  writew((u16)(s16)sample,a6_af_mca+0x28);
  a6_ac_slot=(a6_ac_slot+1)&7;
 }
 return 0;
}
static int a6_ac_get(u32 reg,u8 *value)
{
 u8 reply[5];int ret=a6_ac_read_reg(reg,reply);
 if(!ret)*value=reply[4];return ret;
}
static int a6_ac_put(u32 reg,u8 value,unsigned int phase)
{
 u8 reply[5],rb=0;int ret;unsigned int n=a6_ac_log_count;
 if(n>=ARRAY_SIZE(a6_ac_log))return -EOVERFLOW;
 /* A timed-out write may have reached the codec. Dirty before submission. */
 for(unsigned int i=0;i<a6_ac_preimages;i++)if(a6_ac_profile_registers[i]==reg)a6_ac_dirty[i]=1;
 ret=a6_ac_transfer(reg,reply,true,value);
 if(!ret)ret=a6_ac_get(reg,&rb);
 if(!ret && rb!=value)ret=-EIO;
 a6_ac_log[n][0]=reg;a6_ac_log[n][1]=phase;a6_ac_log[n][2]=value;
 a6_ac_log[n][3]=rb;a6_ac_log[n][4]=ret;a6_ac_log[n][5]=a6_at_samples;
 a6_ac_log_count++;return ret;
}
static int a6_ac_ops(const u32 (*ops)[4],unsigned int count,unsigned int phase)
{
 unsigned int i;int ret;u8 v;
 for(i=0;i<count;i++) {
  if(atomic_read(&a6_at_expired))return -ETIMEDOUT;
  if(ops[i][1]==2){ret=a6_at_wait(ops[i][3]);if(ret)return ret;continue;}
  v=ops[i][3];
  if(ops[i][1]==1){ret=a6_ac_get(ops[i][0],&v);if(ret)return ret;v=(v&~ops[i][2])|ops[i][3];}
  ret=a6_ac_put(ops[i][0],v,phase);if(ret)return ret;
 }
 return 0;
}
static enum hrtimer_restart a6_ac_timeout(struct hrtimer *t)
{
 /* SPI is sleep-free, bounded10ms; the caller observes this flag, mutes
  * synchronously, then powers down before removing the serial clocks. */
 atomic_set(&a6_at_expired,1);return HRTIMER_NORESTART;
}
static int a6_ac_play_locked(void)
{
 bool route=false,timer=false;int ret=0,cr;unsigned int i,loops=0;
 u32 level,v,tx_control,serial_control;u64 measured,delta,setup_started=ktime_get_ns();u8 pd;
 memset(a6_ac_reference_state,0,sizeof(a6_ac_reference_state));
 a6_ac_play_attempted=true;a6_ac_output_enabled=false;
 a6_ac_log_count=a6_ac_preimages=a6_ac_slot=a6_ac_peak_level=a6_ac_drain_rate=0;
 memset(a6_ac_dirty,0,sizeof(a6_ac_dirty));memset(a6_ac_saved,0,sizeof(a6_ac_saved));memset(a6_ac_restored,0,sizeof(a6_ac_restored));
 /* B1 observed on this phone. Never apply the A0-only patch or guess a revision. */
 if(a6_ac_reply[0][4]!=0xb1)return -ENODEV;
 if(readl(a6_touch_gpio+42*4)!=0x202)return -EBUSY;
 for(i=0;i<2;i++) {
  v=readl(a6_ai_switch+(i ? 0x24 : 0x10));a6_ac_route[i][0]=v;
  if(v==U32_MAX || v!=readl(a6_ai_switch+(i ? 0x24 : 0x10)) || (v&(i ? 0xf0f : 0xf01f)))return -EBUSY;
 }
 /* Get every preimage before the first codec write. */
 for(i=0;i<ARRAY_SIZE(a6_ac_profile_registers);i++) {
  ret=a6_ac_get(a6_ac_profile_registers[i],&a6_ac_saved[i]);if(ret)goto stop;
  a6_ac_preimages++;
  if(ktime_get_ns()-setup_started>3000000000ULL){ret=-ETIMEDOUT;goto stop;}
 }
 /* Stock shutdown baseline required: refuse an inherited active codec. */
 if(!(a6_ac_controls[0]&1) || (a6_ac_controls[11]&0xa0)!=0xa0){ret=-EBUSY;goto stop;}
 ret=a6_at_voltage(0);if(ret)goto stop;
 hrtimer_setup(&a6_at_timer,a6_ac_timeout,CLOCK_MONOTONIC,HRTIMER_MODE_REL);
 atomic_set(&a6_at_expired,0);hrtimer_start(&a6_at_timer,ms_to_ktime(4000),HRTIMER_MODE_REL);timer=true;
 ret=a6_at_reference ? a6_ac_ops(a6_ac_reference_init,ARRAY_SIZE(a6_ac_reference_init),0) : a6_ac_ops(a6_ac_muted_init,ARRAY_SIZE(a6_ac_muted_init),0);if(ret)goto stop;
 /* Restart the known stock stream from a flushed FIFO. This fixes the
  * eight-slot word origin before slot2 gets any nonzero sample. */
 tx_control=readl(a6_af_mca+24)&~1U;serial_control=readl(a6_af_mca+12)&~2U;
 writel(tx_control,a6_af_mca+24);writel(serial_control,a6_af_mca+12);
 if(readl(a6_af_mca+24)!=tx_control || readl(a6_af_mca+12)!=serial_control){ret=-EIO;goto stop;}
 writel(0x301,a6_af_mca+0x44);ret=a6_af_poll(a6_af_mca+0x44,U32_MAX,0);if(ret)goto stop;
 /* Feed zeros before starting the serial clocks or unmuting output. */
 a6_at_feeding=true;writel(readl(a6_af_mca+0x40)&0x3000,a6_af_mca+0x40);
 ret=a6_ac_feed();if(ret)goto stop;
 writel(tx_control|1,a6_af_mca+24);writel(serial_control|2,a6_af_mca+12);
 if(readl(a6_af_mca+24)!=(tx_control|1) || readl(a6_af_mca+12)!=(serial_control|2)){ret=-EIO;goto stop;}
 if(!(a6_at_reference && (a6_at_variant&4))) {
 level=readl(a6_af_mca+0x40)&255;measured=ktime_get_ns();udelay(100);
 v=readl(a6_af_mca+0x40);delta=ktime_get_ns()-measured;
 if(!delta || (v&255)>=level || !(v&255) || (v&0x2000)){ret=-EIO;goto stop;}
 a6_ac_drain_rate=div_u64((u64)(level-(v&255))*1000000000,(u32)delta);
 if(a6_ac_drain_rate<300000 || a6_ac_drain_rate>450000){ret=-ERANGE;goto stop;}
 }
 /* Reference-only codec: no codec analog output or serial TX. Verify
  * the stock XSP clock-role initialization before the amp touches pin2. */
 if(a6_at_reference) {
  u8 xsp,format,mute,vsp;
  ret=a6_ac_get(0x2e,&xsp);if(ret)goto stop;
  ret=a6_ac_get(0x2f,&format);if(ret)goto stop;
  ret=a6_ac_get(0x24f,&mute);if(ret)goto stop;
  ret=a6_ac_get(0x13,&vsp);if(ret)goto stop;
  a6_ac_reference_state[0]=xsp;a6_ac_reference_state[1]=format;a6_ac_reference_state[2]=mute;a6_ac_reference_state[3]=vsp;
  if(xsp!=0x80 || format || (mute&0xa0)!=0xa0 || (vsp&0xc0)!=0xc0){ret=-EIO;goto stop;}
  hrtimer_cancel(&a6_at_timer);timer=false;
  a6_at_feeding=false;a6_at_codec=false;
  /* Existing amplifier code owns its independent GPIO42 watchdog, I2C
   * lock, monitor capture and exact route restore. XSP stays RX-only. */
  a6_af_read_amp();ret=a6_ai_result;a6_at_codec=true;
  goto stop;
 }
 /* Verified stock switch convergence: MCA0 master -> pin4/VSP. */
 route=true;writel(a6_ac_route[0][0]|0xf014,a6_ai_switch+0x10);
 writel(a6_ac_route[1][0]|0x400,a6_ai_switch+0x24);
 for(i=0;i<2;i++) {
  a6_ac_route[i][1]=readl(a6_ai_switch+(i ? 0x24 : 0x10));
  if(a6_ac_route[i][1]!=(a6_ac_route[i][0]|(i ? 0x400 : 0xf014))){ret=-EIO;goto stop;}
 }
 ret=a6_ac_ops(a6_ac_receiver_enable,ARRAY_SIZE(a6_ac_receiver_enable),1);if(ret)goto stop;
 a6_ac_output_enabled=true;
 ret=a6_ac_feed();if(ret)goto stop;
 writel(readl(a6_af_mca+0x40)&0x1000,a6_af_mca+0x40);
 a6_at_wave_start=ktime_get_ns();a6_at_wave=true;
 while(ktime_get_ns()-a6_at_wave_start<1000000000ULL) {
  ret=a6_ac_feed();if(ret)goto stop;
  if(ktime_get_ns()-a6_at_wave_start>=500000000ULL && !a6_at_mv[1]){ret=a6_at_voltage(1);if(ret)goto stop;}
  if(++loops>240000){ret=-ETIMEDOUT;goto stop;}udelay(25);
 }
 a6_at_elapsed_us=div_u64(ktime_get_ns()-a6_at_wave_start,1000);
 a6_at_wave=false;ret=a6_at_wait(2);if(ret)goto stop;
 ret=a6_ac_ops(a6_ac_receiver_mute,ARRAY_SIZE(a6_ac_receiver_mute),2);if(ret)goto stop;
 ret=a6_at_voltage(2);
stop:
 /* Cleanup never feeds nonzero samples or depends on the expired timer.
  * Try mute and global power-down even after a partial SPI submission. */
 a6_at_wave=a6_at_feeding=false;
 if(timer)hrtimer_cancel(&a6_at_timer);
 if(a6_ac_preimages==ARRAY_SIZE(a6_ac_profile_registers)) {
  bool dirty=false;for(i=0;i<a6_ac_preimages;i++)if(a6_ac_dirty[i])dirty=true;
  if(dirty) {
   cr=a6_ac_get(0x24f,&pd);if(!cr)cr=a6_ac_put(0x24f,pd|0xa0,3);if(cr)a6_ac_cleanup=-EUCLEAN;
   cr=a6_ac_get(6,&pd);if(!cr)cr=a6_ac_put(6,pd|1,3);if(cr)a6_ac_cleanup=-EUCLEAN;
  }
 }
 /* Restore all submitted register writes, including timed-out ones. */
 for(i=a6_ac_preimages;i-->0;) {
  if(a6_ac_dirty[i] && a6_ac_put(a6_ac_profile_registers[i],a6_ac_saved[i],4))a6_ac_cleanup=-EUCLEAN;
  cr=a6_ac_get(a6_ac_profile_registers[i],&a6_ac_restored[i]);
  if(cr || a6_ac_restored[i]!=a6_ac_saved[i])a6_ac_cleanup=-EUCLEAN;
 }
 if(route)for(i=0;i<2;i++) {
  writel(a6_ac_route[i][0],a6_ai_switch+(i ? 0x24 : 0x10));
  a6_ac_route[i][2]=readl(a6_ai_switch+(i ? 0x24 : 0x10));
  if(a6_ac_route[i][2]!=a6_ac_route[i][0])a6_ac_cleanup=-EUCLEAN;
 }
 a6_at_status_after=readl(a6_af_mca+0x40);
 return a6_ac_cleanup ? a6_ac_cleanup : ret;
}
static ssize_t a6_ac_play_status(char *buf,ssize_t n)
{
 unsigned int i;
 n+=sysfs_emit_at(buf,n,"codec_receiver reference_only=%u attempted=%u enabled=%u preimages=%u log_count=%u drain_words_hz=%u fifo_peak=%u\n",a6_at_reference,a6_ac_play_attempted,a6_ac_output_enabled,a6_ac_preimages,a6_ac_log_count,a6_ac_drain_rate,a6_ac_peak_level);
 n+=sysfs_emit_at(buf,n,"codec_reference_2e_2f_24f_13=%02x,%02x,%02x,%02x\n",a6_ac_reference_state[0],a6_ac_reference_state[1],a6_ac_reference_state[2],a6_ac_reference_state[3]);
 for(i=0;i<a6_ac_preimages;i++)n+=sysfs_emit_at(buf,n,"codec_restore_%04x=%02x/%02x\n",a6_ac_profile_registers[i],a6_ac_saved[i],a6_ac_restored[i]);
 for(i=0;i<2;i++)n+=sysfs_emit_at(buf,n,"codec_route_%02x=%08x/%08x/%08x\n",i ? 0x24 : 0x10,a6_ac_route[i][0],a6_ac_route[i][1],a6_ac_route[i][2]);
 n+=sysfs_emit_at(buf,n,"codec_mca_profile=");
 for(i=0;i<ARRAY_SIZE(a6_ac_mca_config);i++)n+=sysfs_emit_at(buf,n,"%08x%s",a6_ac_mca_config[i],i+1==ARRAY_SIZE(a6_ac_mca_config) ? "\n" : ",");
 return n;
}
#ifndef A6_AUDIO_CODEC_TEST
static ssize_t a6_ac_read_log(struct file *f,struct kobject *k,const struct bin_attribute *a,char *buf,loff_t off,size_t count)
{
 ssize_t ret=0;size_t size;if(!capable(CAP_SYS_RAWIO))return -EPERM;
 mutex_lock(&a6_touch_lock);size=a6_ac_log_count*sizeof(a6_ac_log[0]);
 if(off>=0 && off<size){count=min(count,size-(size_t)off);memcpy(buf,(char *)a6_ac_log+off,count);ret=count;}
 mutex_unlock(&a6_touch_lock);return ret;
}
static struct bin_attribute a6_ac_log_attr={.attr={.name="codec_write_readbacks",.mode=0400},.size=sizeof(a6_ac_log),.read=a6_ac_read_log};
#endif

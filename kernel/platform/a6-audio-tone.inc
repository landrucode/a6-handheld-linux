// SPDX-License-Identifier: GPL-2.0-only
/* Bounded N42 DAC-only candidate. Caller holds the charger I2C mutex.
 * Generated stock operations precede this source; never embed factory bytes
 * in the repository. Neither a DMA channel nor the AE2 core is started.
 */
#ifndef A6_AUDIO_TONE_TEST
#include <linux/hrtimer.h>
#include <linux/math64.h>
#endif
static bool a6_at_requested, a6_at_feeding, a6_at_wave;
static atomic_t a6_at_expired = ATOMIC_INIT(0);
static struct hrtimer a6_at_timer;
static u64 a6_at_wave_start,a6_at_last_feed,a6_at_max_gap;
static unsigned int a6_at_drain_hz, a6_at_elapsed_us;
static unsigned int a6_at_count, a6_at_samples, a6_at_mv[3], a6_at_min_mv;
static u32 a6_at_routes[2][3], a6_at_status_before, a6_at_status_after;
static unsigned char a6_at_log[128][4];
static unsigned char a6_at_faults[3][4];
static u32 a6_at_alive[3];
static unsigned int a6_at_alive_edges;
static u64 a6_at_alive_time, a6_at_alive_interval;
static bool a6_at_alive_active;
static unsigned int a6_at_rx_count, a6_at_rx_nonzero, a6_at_rx_peak;
static u16 a6_at_rx_first[16];
static u32 a6_at_rx_status;
static bool a6_at_rx_active;
static unsigned int a6_at_variant, a6_at_peak=32;
static bool a6_at_supplies, a6_at_reference, a6_at_stock44100, a6_at_all_slots, a6_at_ios_route, a6_at_ios_amp;
static int a6_at_frame_sample;
static unsigned int a6_at_frame_limit=48000;
static unsigned int a6_at_silent_drain_words,a6_at_silent_drain_us;
static unsigned int a6_at_reference_slot;
static u32 a6_at_ext[2][3], a6_at_ext_observed[2];
static u16 a6_at_monitor[3][512];
static unsigned int a6_at_monitor_count[3], a6_at_monitor_phase[3], a6_at_monitor_stage;
static u8 a6_at_play_state[7];
static const u8 a6_at_power_regs[]={6,7,8,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f,0x10,0x11,0x12,0x36};
static u8 a6_at_power_state[3][13];
static int a6_at_error;
static void a6_at_reset_run(void)
{
	a6_at_stock44100=a6_at_all_slots=a6_at_ios_route=a6_at_ios_amp=false;a6_at_frame_sample=0;a6_at_frame_limit=48000;a6_at_silent_drain_words=a6_at_silent_drain_us=0;
	a6_at_feeding=a6_at_wave=false;a6_at_peak=32;a6_at_supplies=false;
	a6_at_wave_start=0;a6_at_last_feed=a6_at_max_gap=0;a6_at_reference=false;a6_at_reference_slot=0;
	a6_at_drain_hz=a6_at_elapsed_us=0;
	a6_at_count=a6_at_samples=a6_at_min_mv=0;
	a6_at_rx_count=a6_at_rx_nonzero=a6_at_rx_peak=0;a6_at_rx_status=0;a6_at_rx_active=false;
	memset(a6_at_rx_first,0,sizeof(a6_at_rx_first));
	memset(a6_at_monitor,0,sizeof(a6_at_monitor));memset(a6_at_monitor_count,0,sizeof(a6_at_monitor_count));memset(a6_at_monitor_phase,0,sizeof(a6_at_monitor_phase));a6_at_monitor_stage=0;
	memset(a6_at_ext,0,sizeof(a6_at_ext));memset(a6_at_ext_observed,0,sizeof(a6_at_ext_observed));memset(a6_at_play_state,0,sizeof(a6_at_play_state));
	a6_at_error=0;a6_at_status_before=a6_at_status_after=0;
	memset(a6_at_mv,0,sizeof(a6_at_mv));
	memset(a6_at_routes,0,sizeof(a6_at_routes));
	memset(a6_at_log,0,sizeof(a6_at_log));
	memset(a6_at_faults,0,sizeof(a6_at_faults));memset(a6_at_power_state,0,sizeof(a6_at_power_state));
	memset(a6_at_alive,0,sizeof(a6_at_alive));
	a6_at_alive_edges=0;a6_at_alive_time=0;a6_at_alive_interval=0;a6_at_alive_active=false;
	atomic_set(&a6_at_expired,0);
}
static const signed char a6_at_sine[48] = {0,1,2,3,4,5,6,6,7,7,8,8,8,8,8,7,7,6,6,5,4,3,2,1,0,-1,-2,-3,-4,-5,-6,-6,-7,-7,-8,-8,-8,-8,-8,-7,-7,-6,-6,-5,-4,-3,-2,-1};
static enum hrtimer_restart a6_at_timeout(struct hrtimer *t)
{
	/* Reset is independent of an I2C transaction or a sleeping worker. */
	atomic_set(&a6_at_expired,1);
	writel(0x202,a6_touch_gpio+42*4);
	return HRTIMER_NORESTART;
}
static int a6_at_refill_tx(void)
{
	u32 s;unsigned int n;int sample;
	s=readl(a6_af_mca+0x40);
	if(s==U32_MAX || (s&255)>128 || (s&0x2000))return -EIO;
	/* An underrun after unmute aborts immediately; initial empty state is
	 * acknowledged while muted. Keep 64..96 words queued thereafter. */
	if(a6_at_wave && (s&0x1000))return -EPIPE;
	if((s&255)>=64)return 0;
	for(n=s&255;n<96;n++) {
		sample=(a6_at_all_slots && a6_at_reference_slot) ? a6_at_frame_sample : 0;
		if(a6_at_all_slots && !a6_at_reference_slot)a6_at_frame_sample=0;
		if(a6_at_wave && (!(a6_at_reference || a6_at_all_slots) || !a6_at_reference_slot) && a6_at_samples<a6_at_frame_limit) {
			unsigned int elapsed=div_u64(ktime_get_ns()-a6_at_wave_start,1000);
			unsigned int phase=(u32)div_u64((u64)a6_at_samples*48000,a6_at_stock44100 ? a6_at_frame_limit : a6_at_drain_hz)%48;
			unsigned int ramp=elapsed<500000 ? elapsed : (elapsed<1000000 ? 1000000-elapsed : 0);
			sample=(int)a6_at_peak*a6_at_sine[phase]/8;
			if(ramp<20000)sample=sample*(int)ramp/20000;
			a6_at_samples++;
			if(a6_at_all_slots)a6_at_frame_sample=sample;
		}
		/* Stock MCA DMA chooses two-byte transfers for width <=16. */
		writew((u16)(s16)sample,a6_af_mca+0x28);
		if(a6_at_reference || a6_at_all_slots)a6_at_reference_slot=(a6_at_reference_slot+1)&7;
	}
	return 0;
}
static int a6_at_feed(void)
{
	int ret;
	#ifndef A6_AUDIO_TONE_TEST
	if(a6_at_codec)return a6_ac_feed();
#endif
	if(atomic_read(&a6_at_expired))return -ETIMEDOUT;
	if(a6_at_alive_active) {
		u64 elapsed=ktime_get_ns()-a6_at_alive_time;
		if(elapsed>40000000)return -ETIMEDOUT;
		if(elapsed>=a6_at_alive_interval) {
			a6_at_alive[1]^=1;writel(a6_at_alive[1],a6_touch_gpio+9*4);
			if(readl(a6_touch_gpio+9*4)!=a6_at_alive[1])return -EIO;
			a6_at_alive_edges++;a6_at_alive_time=ktime_get_ns();a6_at_alive_interval=20000000ULL;
		}
	}
	if(!a6_at_feeding)return 0;
	{u64 now=ktime_get_ns();if(a6_at_last_feed && now-a6_at_last_feed>a6_at_max_gap)a6_at_max_gap=now-a6_at_last_feed;a6_at_last_feed=now;}
	if(a6_at_reference || a6_at_stock44100){ret=a6_at_refill_tx();if(ret)return ret;}
	if(a6_at_rx_active) {
		unsigned int r;
		a6_at_rx_status=readl(a6_af_mca+0x40);
		r=(a6_at_rx_status>>16)&255;
		/* Candidate RX occupancy field, tested empirically; bounded reads. */
		if(r>128 || (a6_at_rx_status&0x20000000))return -EOVERFLOW;
		if(r>a6_at_rx_peak)a6_at_rx_peak=r;
		if(r>32)r=32;
		while(r--) {
			u16 sample=readw(a6_af_mca+0x3c);
			if(a6_at_rx_count<16)a6_at_rx_first[a6_at_rx_count]=sample;
			if(a6_at_monitor_stage<3 && a6_at_monitor_count[a6_at_monitor_stage]<512) {
				if(!a6_at_monitor_count[a6_at_monitor_stage])
					a6_at_monitor_phase[a6_at_monitor_stage]=a6_at_rx_count%(a6_at_supplies ? 4 : 2);
				a6_at_monitor[a6_at_monitor_stage][a6_at_monitor_count[a6_at_monitor_stage]++]=sample;
			}
			a6_at_rx_count++;if(sample)a6_at_rx_nonzero++;
			/* Full eight-slot RX at the admitted96k frame/s ceiling for the
			 * unchanged2s watchdog; this counts words, not stored samples. */
			if(a6_at_rx_count>(a6_at_reference ? 1536000U : 240000U))return -EOVERFLOW;
		}
	}
	return a6_at_refill_tx();
}

static int a6_at_wait(unsigned int ms)
{
	u64 start=ktime_get_ns();unsigned int i=0;int ret;
	/* Stock IOSleep delays are elapsed milliseconds. Counted udelay calls
	 * ran shorter on this boot; preserve settling time and FIFO servicing. */
	while(ktime_get_ns()-start<(u64)ms*1000000) {
		if(atomic_read(&a6_at_expired))return -ETIMEDOUT;
		ret=a6_at_feed();if(ret)return ret;
		if(++i>ms*1000+100)return -ETIMEDOUT;
		udelay((a6_at_reference || a6_at_stock44100) ? 10 : 100);
	}
	return 0;
}
static int a6_at_xfer(unsigned int addr,u8 reg,u8 *value,bool write)
{
	u32 s,need=A6_POWER_TX|A6_POWER_XEN|(write ? 0 : A6_POWER_RX);
	unsigned int i; int ret;
	if(addr!=0x40 && (addr!=0x74 || reg<0x48 || reg>0x4a || (write && reg!=0x48)))return -EINVAL;
	/* Refill before submitting an enable write, not only while polling its
	 * completion. A preceding settling wait can end below the refill mark. */
	ret=a6_at_feed();if(ret)return ret;
	s=readl(a6_touch_i2c+0x14);if(!a6_power_is_idle(s))return -EBUSY;
	writel(s,a6_touch_i2c+0x14);writel(0x100|(addr<<1),a6_touch_i2c);
	if(write) {writel(reg,a6_touch_i2c);writel(0x200|*value,a6_touch_i2c);}
	else {writel(0x200|reg,a6_touch_i2c);writel(0x101|(addr<<1),a6_touch_i2c);writel(0x601,a6_touch_i2c);}
	ret=-ETIMEDOUT;
	for(i=0;i<10000;i++) {
		ret=a6_at_feed();if(ret)break;
		s=readl(a6_touch_i2c+0x14);
		if(s==U32_MAX || (s&A6_POWER_ERR)){ret=(s&BIT(21)) ? -ENXIO : -EIO;break;}
		if(!(s&A6_POWER_XIP) && (s&need)==need) {
			ret=0;if(!write)*value=readl(a6_touch_i2c+4)&255;break;
		}
		ret=-ETIMEDOUT;udelay(10);
	}
	/* Acknowledge completion before recovery. TX-ready alone is not
	 * proof that the just-submitted STOP has completed. */
	if(!ret)writel(A6_POWER_XEN,a6_touch_i2c+0x14);
	if(!a6_power_recover())return -EUCLEAN;
	return ret;
}
static int a6_at_voltage(unsigned int index)
{
	u8 saved=0,v,lo=0,hi=0,verify=0;int ret,cr;
	ret=a6_at_xfer(0x74,0x48,&saved,false);if(ret)return ret;
	if(saved&0x60)return -EBUSY;
	v=(saved&0x80)|0x24;
	ret=a6_at_xfer(0x74,0x48,&v,true);
	if(!ret)ret=a6_at_wait(10);
	if(!ret)ret=a6_at_xfer(0x74,0x49,&lo,false);
	if(!ret)ret=a6_at_xfer(0x74,0x4a,&hi,false);
	/* Restore even if the submitted ADC write timed out. Reset has already
	 * been asserted by the watchdog if its deadline was exceeded. */
	if(ret){writel(0x202,a6_touch_gpio+42*4);a6_at_feeding=false;}
	cr=a6_at_xfer(0x74,0x48,&saved,true);
	if(!cr)cr=a6_at_xfer(0x74,0x48,&verify,false);
	if(cr || verify!=saved){a6_af_cleanup=-EUCLEAN;return -EUCLEAN;}
	if(ret)return ret;
	a6_at_mv[index]=2500+((lo&15)|(hi<<4))*32000/65536;
	if(!a6_at_min_mv || a6_at_mv[index]<a6_at_min_mv)a6_at_min_mv=a6_at_mv[index];
	return a6_at_mv[index]<3600 ? -ERANGE : 0;
}
static int a6_at_read_faults(unsigned int stage)
{
	unsigned int i;int ret;
	/* Stock reads each status twice: retain both sticky and live values.
	 * No CS35L33-only interpretation or fault-clearing write is applied. */
	for(i=0;i<4;i++) {
		ret=a6_at_xfer(0x40,0x15+i/2,&a6_at_faults[stage][i],false);
		if(ret)return ret;
	}
	return 0;
}
static int a6_at_read_power(unsigned int stage)
{
 unsigned int i;int ret;
 for(i=0;i<ARRAY_SIZE(a6_at_power_regs);i++){ret=a6_at_xfer(0x40,a6_at_power_regs[i],&a6_at_power_state[stage][i],false);if(ret)return ret;}
 return 0;
}
static int a6_at_op(unsigned int index)
{
	const unsigned char *op=a6_at_stock44100 ? a6_at_stock44100_master_ops[index] : a6_at_supplies ? ((a6_at_variant&4) ? a6_at_supply_master_ops[index] : a6_at_supply_ops[index]) : ((a6_at_variant&4) ? a6_at_master_ops[index] : a6_at_ops[index]);u8 v=op[3],old=0,rb=0;int ret;
	const u8 *capture=(const u8 *)a6_memory_capture_copy;
	const u8 *board=capture+0x820;
	bool calib=(a6_memory_capture_copy[513]&4) && a6_memory_capture_copy[517]==20 && a6_memory_capture_copy[0x860/4]==1;
	if(op[0]==4)return a6_at_wait(v);
 if(op[0]==5){
  a6_at_alive[1]^=1;writel(a6_at_alive[1],a6_touch_gpio+9*4);
  if(readl(a6_touch_gpio+9*4)!=a6_at_alive[1])return -EIO;
  a6_at_alive_edges++;return 0;
 }
 if(op[0]==6){
  a6_at_alive_active=!!v;
  a6_at_alive_time=ktime_get_ns();a6_at_alive_interval=1000000ULL;
  return 0;
 }
	if(op[0]==1)return a6_at_xfer(0x40,op[1],&rb,false);
	/* Stock default device-UID is Speaker: calibration bytes0/4. */
	if(op[1]==0x0d)v=(a6_at_variant&4) ? 0x43 : 0x03;
	if(op[1]==0x46)v=calib ? capture[0x850] : board[16];
	if(op[1]==0x3a)v=calib ? (board[12]&0xe0)|(capture[0x854]&31) : board[12];
	if(op[1]==0x18)v=board[19];

	if(op[0]==3) {
		ret=a6_at_xfer(0x40,op[1],&old,false);if(ret)return ret;
		v=(old&~op[2])|v;
	}
	ret=a6_at_xfer(0x40,op[1],&v,true);
	if(ret)return ret;
	ret=a6_at_xfer(0x40,op[1],&rb,false);
	if(a6_at_count<ARRAY_SIZE(a6_at_log)) {
		a6_at_log[a6_at_count][0]=index;a6_at_log[a6_at_count][1]=op[1];
		a6_at_log[a6_at_count][2]=v;a6_at_log[a6_at_count++][3]=rb;
	}
	/* Key unlock00 has write-only semantics; retain its readback as evidence.
	 * A mismatch elsewhere prevents subsequent enable operations. */
	if(!ret && op[1] && rb!=v)ret=-EIO;
	return ret;
}
static int a6_at_play(void)
{
	unsigned int i,loops=0;int ret=0;bool route=false,alive=false,ext=false;
	u32 v,level;u64 measured,delta;
	/* Live metadata must identify exactly one valid board config. A missing
	 * SRdc/calibration uses the traced stock fallback and this tiny signal. */
	if(a6_memory_capture_copy[512]!=0x53504431 || a6_memory_capture_copy[514]!=1 ||
	   (a6_memory_capture_copy[513]&0x31)!=1 || a6_memory_capture_copy[515]!=20)return -ENODATA;
	/* Firmware populates board bytes12,16,19 at boot. Use those live
	 * inputs at the exact stock write sites; reject any other change. */
	for(i=0;i<20;i++)if(i!=12 && i!=16 && i!=19 && ((u8 *)a6_memory_capture_copy)[0x820+i]!=a6_at_config[i])return -ENODATA;
	/* Stock80db1f24..1f68 ignores unsupported calibration versions. */
	if((a6_memory_capture_copy[513]&4) && a6_memory_capture_copy[517]!=20)return -EINVAL;
	if(a6_af_amp_id!=0xb0)return -ENODEV;
	if(!a6_auto_enabled || a6_auto_fault || a6_auto_paused || !a6_low_enabled || a6_low_triggered ||
	   a6_policy_vbat_mv<3600 || a6_policy_tbat_c<10 || a6_policy_tbat_c>35)return -EBUSY;
	for(i=0;i<2;i++) {
		v=readl(a6_ai_switch+(i ? 0x24 : 8));a6_at_routes[i][0]=v;
		if(v==U32_MAX || (v&(i ? 0xf0f : 0xf01f)))return -EBUSY;
	}
	a6_at_alive[0]=readl(a6_touch_gpio+9*4);
	if(a6_at_alive[0]==U32_MAX || a6_at_alive[0]!=readl(a6_touch_gpio+9*4))return -EBUSY;
	for(i=0;i<2;i++) {
		a6_at_ext[i][0]=readl(a6_touch_gpio+(90+i)*4);
		if(a6_at_ext[i][0]==U32_MAX || a6_at_ext[i][0]!=readl(a6_touch_gpio+(90+i)*4))return -EBUSY;
	}
	hrtimer_setup(&a6_at_timer,a6_at_timeout,CLOCK_MONOTONIC,HRTIMER_MODE_REL);
	atomic_set(&a6_at_expired,0);
	hrtimer_start(&a6_at_timer,ms_to_ktime(2000),HRTIMER_MODE_REL);
	/* Stock2448 toggles logical state; DT polarity1 maps0/1 to202/203.
	 * Enable2ee8..2ef4 kicks three times, first timer1ms, then20ms. */
	alive=true;a6_at_alive[1]=(a6_at_alive[0]&~0x6fU)|2U;a6_at_alive_edges=0;
	if(!a6_at_stock44100)for(i=0;i<3;i++) {
		a6_at_alive[1]^=1;writel(a6_at_alive[1],a6_touch_gpio+9*4);
		if(readl(a6_touch_gpio+9*4)!=a6_at_alive[1]){ret=-EIO;goto stop;}
		a6_at_alive_edges++;
	}
	a6_at_alive_time=ktime_get_ns();a6_at_alive_interval=1000000ULL;a6_at_alive_active=!a6_at_stock44100;
	ext=true;
	for(i=0;i<2;i++) {
		a6_at_ext[i][1]=(a6_at_ext[i][0]&~0x6fU)|2U|((a6_at_variant>>i)&1);
		writel(a6_at_ext[i][1],a6_touch_gpio+(90+i)*4);
	}
	/* Stock external-switch dispatcher80a5deca waits50ms after a change.
	 * GPIO provider preserves bits outside6f; bit0 is observed pin state. */
	ret=a6_at_wait(50);if(ret)goto stop;
	for(i=0;i<2;i++)a6_at_ext_observed[i]=readl(a6_touch_gpio+(90+i)*4);
	for(i=0;i<2;i++)if(a6_at_ext_observed[i]!=a6_at_ext[i][1]){ret=-EIO;goto stop;}
	if(a6_at_reference) {
		u32 tx_control=readl(a6_af_mca+24)&~1U;
		u32 serial_control=readl(a6_af_mca+12)&~2U;
		writel(tx_control,a6_af_mca+24);writel(serial_control,a6_af_mca+12);
		if(readl(a6_af_mca+24)!=tx_control || readl(a6_af_mca+12)!=serial_control){ret=-EIO;goto stop;}
		writel(0x301,a6_af_mca+0x44);
		ret=a6_af_poll(a6_af_mca+0x44,U32_MAX,0);if(ret)goto stop;
		a6_at_reference_slot=0;a6_at_feeding=true;
		writel(readl(a6_af_mca+0x40)&0x3000,a6_af_mca+0x40);
		ret=a6_at_feed();if(ret)goto stop;
		writel(tx_control|1,a6_af_mca+24);writel(serial_control|2,a6_af_mca+12);
		if(readl(a6_af_mca+24)!=(tx_control|1) || readl(a6_af_mca+12)!=(serial_control|2)){ret=-EIO;goto stop;}
	}
	a6_at_feeding=true;a6_at_status_before=readl(a6_af_mca+0x40);
	writel(a6_at_status_before&0x3000,a6_af_mca+0x40);
	ret=a6_at_feed();if(ret)goto stop;
	route=true;
	/* Stock route flag2 for MCA master: clock direction/select bits14,
	 * not the flag1 external-clock route with switch24 low nibble2. */
	writel(a6_at_routes[0][0]|((a6_at_variant&4) ? 0xf000 : 0xf014),a6_ai_switch+8);
	writel(a6_at_ios_route ? 2U : ((a6_at_routes[1][0]&~0xf0f)|((a6_at_variant&4) ? 0x202U : 0x200U)),a6_ai_switch+0x24);
	for(i=0;i<2;i++) {
		a6_at_routes[i][1]=readl(a6_ai_switch+(i ? 0x24 : 8));
		if(a6_at_routes[i][1]!=(i && a6_at_ios_route ? 2U : (i ? ((a6_at_routes[i][0]&~0xf0fU)|((a6_at_variant&4) ? 0x202U : 0x200U)) : (a6_at_routes[i][0]|((a6_at_variant&4) ? 0xf000U : 0xf014U))))){ret=-EIO;goto stop;}
	}
	ret=a6_at_voltage(0);if(ret)goto stop;
	for(i=0;i<(a6_at_stock44100 ? A6_AT_STOCK44100_MASTER_SHUTDOWN : ((a6_at_variant&4) ? A6_AT_MASTER_SHUTDOWN : A6_AT_SHUTDOWN));i++){ret=a6_at_op(i);if(ret)goto stop;}
	/* Captured audible stock values, deliberately applied after the replay.
	 * Log each write and require its exact readback before any tone. */
	if(a6_at_ios_amp) {
		const u8 regs[]={7,8,0x10},values[]={0xf8,0x49,0};
		for(i=0;i<ARRAY_SIZE(regs);i++) {
			u8 value=values[i],rb=0;
			ret=a6_at_xfer(0x40,regs[i],&value,true);if(ret)goto stop;
			ret=a6_at_xfer(0x40,regs[i],&rb,false);
			if(a6_at_count<ARRAY_SIZE(a6_at_log)) {
				a6_at_log[a6_at_count][0]=0xe0+i;a6_at_log[a6_at_count][1]=regs[i];
				a6_at_log[a6_at_count][2]=value;a6_at_log[a6_at_count++][3]=rb;
			}
			if(ret || rb!=value){if(!ret)ret=-EIO;goto stop;}
		}
	}
	/* Confirm stock default volume/gain and every relevant play-state bit.
	 * Stock default digital19, analog gain70; no maximum-gain guesses. */
	{
		const u8 regs[]={6,7,8,0x0d,0x0f,0x10,0x12};
		for(i=0;i<ARRAY_SIZE(regs);i++) {ret=a6_at_xfer(0x40,regs[i],&a6_at_play_state[i],false);if(ret)goto stop;}
		if((a6_at_play_state[0]&0x85) || (!a6_at_ios_amp && (a6_at_play_state[1]&0x0e)) ||
		   a6_at_play_state[1]!=(a6_at_ios_amp ? 0xf8 : (a6_at_supplies ? 0 : 0x30)) ||
		   (a6_at_play_state[2]&0x80) || (a6_at_ios_amp && a6_at_play_state[2]!=0x49) || (a6_at_play_state[4]&0x10) ||
		   a6_at_play_state[3]!=((a6_at_variant&4)?0x43:3) ||
		   a6_at_play_state[5]!=(a6_at_ios_amp ? 0 : 0x19) || (a6_at_play_state[6]&0xf0)!=0x70){ret=-EIO;goto stop;}
	}
	ret=a6_at_read_faults(0);if(ret)goto stop;
 ret=a6_at_read_power(0);if(ret)goto stop;
	if(a6_at_stock44100) {
		u64 total_ns=0;unsigned int words=0,trial;
		/* Observed slave role: neither clock-generator enable bit may be set.
		 * Silence only; refill between bounded occupancy measurements. */
		if(readl(a6_af_mca+12)&5U){ret=-EIO;goto stop;}
		for(trial=0;trial<8;trial++) {
			ret=a6_at_feed();if(ret)goto stop;
			level=readl(a6_af_mca+0x40)&255;measured=ktime_get_ns();
			{unsigned int spins=0;u64 window_ns=a6_at_all_slots ? 100000 : 500000;
			 while(ktime_get_ns()-measured<window_ns) {
				if(++spins>1000 || atomic_read(&a6_at_expired)){ret=-ETIMEDOUT;goto stop;}
				udelay(10);
			 }}
			v=readl(a6_af_mca+0x40);delta=ktime_get_ns()-measured;
			if(!delta || (v&255)>=level || !(v&255) || (v&0x2000)){ret=-EIO;goto stop;}
			words+=level-(v&255);total_ns+=delta;
		}
		a6_at_silent_drain_words=words;a6_at_silent_drain_us=div_u64(total_ns,1000);
		a6_at_drain_hz=div_u64((u64)words*1000000000,(u32)total_ns);
		if(a6_at_all_slots)a6_at_drain_hz/=8;
	} else {
	level=readl(a6_af_mca+0x40)&255;measured=ktime_get_ns();
	udelay(a6_at_reference ? 100 : 500);v=readl(a6_af_mca+0x40);delta=ktime_get_ns()-measured;
	if(!delta || (v&255)>=level || !(v&255) || (v&0x2000)){ret=-EIO;goto stop;}
	a6_at_drain_hz=div_u64((u64)(level-(v&255))*1000000000,(u32)delta);
	if(a6_at_reference)a6_at_drain_hz/=8;
	}
	if(a6_at_stock44100 && (a6_at_drain_hz<(a6_at_ios_amp ? 45000U : 41000U) || a6_at_drain_hz>(a6_at_ios_amp ? 51000U : 47000U))){ret=-ERANGE;goto stop;}
	if(a6_at_drain_hz<4000 || a6_at_drain_hz>96000){ret=-ERANGE;goto stop;}
	ret=a6_at_feed();if(ret)goto stop;
	/* Start at zero and ramp to ±32/32768; 48000 nominal48k samples. */
	writel(readl(a6_af_mca+0x40)&0x1000,a6_af_mca+0x40);
	if(a6_at_ios_route) {
		if(readl(a6_af_mca+0x2c)!=0x10a){ret=-EIO;goto stop;}
	} else {
		writel(0x10b,a6_af_mca+0x2c);
		if(readl(a6_af_mca+0x2c)!=0x10b){ret=-EIO;goto stop;}
		a6_at_rx_active=true;
	}
	a6_at_monitor_stage=0;ret=a6_at_wait(20);if(ret)goto stop;
	a6_at_monitor_stage=3;
	a6_at_wave_start=ktime_get_ns();a6_at_wave=true;
	while(ktime_get_ns()-a6_at_wave_start<1000000000) {
		ret=a6_at_feed();if(ret)goto stop;
		if(ktime_get_ns()-a6_at_wave_start>=500000000 && !a6_at_mv[1]){
			a6_at_monitor_stage=1;ret=a6_at_wait(20);if(ret)goto stop;a6_at_monitor_stage=3;
			ret=a6_at_voltage(1);if(ret)goto stop;
			ret=a6_at_read_faults(1);if(ret)goto stop;
   ret=a6_at_read_power(1);if(ret)goto stop;
		}
		if(++loops>240000){ret=-ETIMEDOUT;goto stop;}udelay((a6_at_reference || a6_at_stock44100) ? 10 : 100);
	}
	a6_at_elapsed_us=div_u64(ktime_get_ns()-a6_at_wave_start,1000);
	a6_at_wave=false;a6_at_monitor_stage=2;ret=a6_at_wait(20);if(ret)goto stop;
	ret=a6_at_read_faults(2);if(ret)goto stop;
 ret=a6_at_read_power(2);if(ret)goto stop;
	ret=a6_at_wait(15);if(ret)goto stop;
	for(i=(a6_at_stock44100 ? A6_AT_STOCK44100_MASTER_SHUTDOWN : ((a6_at_variant&4) ? A6_AT_MASTER_SHUTDOWN : A6_AT_SHUTDOWN));i<(a6_at_stock44100 ? ARRAY_SIZE(a6_at_stock44100_master_ops) : ((a6_at_variant&4) ? ARRAY_SIZE(a6_at_master_ops) : ARRAY_SIZE(a6_at_ops)));i++){ret=a6_at_op(i);if(ret)goto stop;}
	ret=a6_at_voltage(2);
stop:
	/* Hard reset first on any error, before route/gate rollback. */
	writel(0x202,a6_touch_gpio+42*4);
	if(readl(a6_touch_gpio+42*4)!=0x202)a6_af_cleanup=-EUCLEAN;
	a6_at_rx_active=false;writel(0x10a,a6_af_mca+0x2c);
	if(readl(a6_af_mca+0x2c)!=0x10a)a6_af_cleanup=-EUCLEAN;
	hrtimer_cancel(&a6_at_timer);
	a6_at_alive_active=false;
	if(alive) {
		writel(a6_at_alive[0],a6_touch_gpio+9*4);
		a6_at_alive[2]=readl(a6_touch_gpio+9*4);
		if(a6_at_alive[2]!=a6_at_alive[0])a6_af_cleanup=-EUCLEAN;
	}
	if(ext) {
		u64 settle_start;
		/* GPIO input readback needs the stock settling interval on both edges.
		 * Amp reset is already asserted and its watchdog is cancelled. */
		for(i=0;i<2;i++)writel(a6_at_ext[i][0],a6_touch_gpio+(90+i)*4);
		settle_start=ktime_get_ns();
		for(i=0;i<10000 && ktime_get_ns()-settle_start<50000000;i++)udelay(10);
	}
	if(ext)for(i=0;i<2;i++) {
		a6_at_ext[i][2]=readl(a6_touch_gpio+(90+i)*4);
		if(a6_at_ext[i][2]!=a6_at_ext[i][0])a6_af_cleanup=-EUCLEAN;
	}
	a6_at_status_after=readl(a6_af_mca+0x40);a6_at_wave=false;a6_at_feeding=false;
	if(route)for(i=0;i<2;i++) {
		writel(a6_at_routes[i][0],a6_ai_switch+(i ? 0x24 : 8));
		a6_at_routes[i][2]=readl(a6_ai_switch+(i ? 0x24 : 8));
		if(a6_at_routes[i][2]!=a6_at_routes[i][0])a6_af_cleanup=-EUCLEAN;
	}
#ifndef A6_AUDIO_TONE_TEST
 a6_af_i2c_snapshot(1);
 for(i=1;i<5;i++)if(a6_af_i2c[0][i]!=a6_af_i2c[1][i])a6_af_cleanup=-EUCLEAN;
 if(!a6_power_is_idle(a6_af_i2c[1][0]))a6_af_cleanup=-EUCLEAN;
#endif
	a6_at_error=ret;return ret;
}

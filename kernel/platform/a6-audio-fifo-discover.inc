// SPDX-License-Identifier: GPL-2.0-only
/* N42 one-shot zero-only FIFO test; optional bounded MCLK/reset/amp ID. */
#define A6_AF_SNAPS 13
#define A6_AF_WORDS (0x1000 / 4)
static void __iomem *a6_af_mca, *a6_af_nco, *a6_af_acs;
static u32 a6_af_dump[A6_AF_SNAPS][A6_AF_WORDS];
static unsigned int a6_af_polls, a6_af_peak;
static unsigned int a6_af_snaps, a6_af_written, a6_af_stage[A6_AF_SNAPS];
static u32 a6_af_ntrace[16][4];
static unsigned int a6_af_nsteps;
static bool a6_af_attempted;
static int a6_af_result, a6_af_cleanup, a6_af_amp = -EAGAIN;
static u32 a6_af_gate[2][3], a6_af_ncos[7][4], a6_af_nc_after[4];
static u32 a6_af_source, a6_af_acs_before, a6_af_acs_after;
static u32 a6_af_i2c[2][5], a6_af_amp_id, a6_af_gpio;
static u32 a6_af_fault[3][5];
/* Stock: layout0 setIIS 810bfbfc..810c0122; width16 table810c2fb0;
 * NCO6 8114e15c..8114e300 uses PMGR+310/+314/+318 only;
 * ACS5 805edef2/805edf0c; TX faults810c152c/810c155e. */
static const u32 a6_af_offsets[] = {8,12,16,20,24,28,32,36,44,48,52,56};
static u32 a6_af_saved[ARRAY_SIZE(a6_af_offsets)], a6_af_restored[ARRAY_SIZE(a6_af_offsets)];

static void a6_af_snapshot(unsigned int stage)
{
	unsigned int i;
	if (a6_af_snaps >= A6_AF_SNAPS) return;
	for (i = 0; i < A6_AF_WORDS; i++)
		/* Data ports consume RX or have undefined TX read semantics. */
		a6_af_dump[a6_af_snaps][i] = (i == 10 || i == 15) ? 0xfeedf1f0 : readl(a6_af_mca + 4*i);
	a6_af_stage[a6_af_snaps++] = stage;
}
static int a6_af_poll(void __iomem *reg, u32 mask, u32 want)
{
	u32 v;
	return readl_poll_timeout(reg, v, v != U32_MAX && (v & mask) == want, 10, 10000);
}
static int a6_af_nwrite(unsigned int off, u32 v)
{
	int ret; unsigned int i = a6_af_nsteps++;
	writel(v, a6_af_nco + 0x310 + off);
	ret = a6_af_poll(a6_af_nco + 0x310, 0x40000002, 0);
	if(i < ARRAY_SIZE(a6_af_ntrace)) {
		a6_af_ntrace[i][0]=off; a6_af_ntrace[i][1]=v;
		a6_af_ntrace[i][2]=readl(a6_af_nco+0x310+off);
		a6_af_ntrace[i][3]=readl(a6_af_nco+0x310);
		if(!ret && off && a6_af_ntrace[i][2]!=v) ret=-EIO;
	}
	return ret;
}
static void a6_af_i2c_snapshot(unsigned int stage)
{
	a6_af_i2c[stage][0] = readl(a6_touch_i2c+0x14);
	a6_af_i2c[stage][1] = readl(a6_touch_i2c+0x18);
	a6_af_i2c[stage][2] = readl(a6_touch_i2c+0x1c);
	a6_af_i2c[stage][3] = readl(a6_touch_i2c+0x28);
	a6_af_i2c[stage][4] = readl(a6_touch_pmgr+0x118);
}
static void a6_af_read_amp_locked(void)
{
	u32 s, needed = A6_POWER_XEN|A6_POWER_TX|A6_POWER_RX;
	unsigned int i;
	a6_af_i2c_snapshot(0);
	a6_af_gpio = readl(a6_touch_gpio + 42*4);
	if (!a6_power_is_idle(a6_af_i2c[0][0]) || a6_af_i2c[0][1] != 0 ||
	    a6_af_i2c[0][2] != 0x104 || a6_af_i2c[0][3] != 1 ||
	    a6_af_i2c[0][4] != 0x2ff) { a6_af_amp = -EBUSY; goto out; }
	if (!(a6_af_gpio & 1)) { a6_af_amp = -EHOSTDOWN; goto out; }
	writel(a6_af_i2c[0][0], a6_touch_i2c+0x14);
	/* Stock mode1: pointer with STOP, then a new read START, one byte. */
	writel(0x180, a6_touch_i2c); writel(0x205, a6_touch_i2c);
	writel(0x181, a6_touch_i2c); writel(0x601, a6_touch_i2c);
	a6_af_amp = -ETIMEDOUT;
	for (i = 0; i < 10000; i++) {
		s = readl(a6_touch_i2c+0x14);
		if (s == U32_MAX || (s & A6_POWER_ERR)) {
			a6_af_amp = (s & BIT(21)) ? -ENXIO : -EIO; break;
		}
		if (!(s & A6_POWER_XIP) && (s & needed) == needed) {
			a6_af_amp_id = readl(a6_touch_i2c+4) & 0xff;
			a6_af_amp = 0; break;
		}
		udelay(10);
	}
	if (!a6_power_recover()) a6_af_cleanup = -EUCLEAN;
out:
	a6_af_i2c_snapshot(1);
	for (i = 1; i < 5; i++)
		if (a6_af_i2c[0][i] != a6_af_i2c[1][i]) a6_af_cleanup = -EUCLEAN;
}
#ifdef A6_AUDIO_AMP_ID
/* Stock Samsung MCLK-only path: nclk=CPU fixed clock=24 MHz, ratio2
 * 811a572a sets 0x114; 811a4bae adds 0x20. No NCO frequency change.
 * i2sR aud2/pin2, packed300003, args(0,20): stock graph converges to
 * switch+48 bit0 only. No serial data route or amp configuration writes. */
static void __iomem *a6_ai_iis, *a6_ai_switch;
static u32 a6_ai_gate[2][3], a6_ai_regs[3][3], a6_ai_nc[2][3];
static u32 a6_ai_acs[3], a6_ai_route[3], a6_ai_reset[3], a6_ai_fixed;
static unsigned int a6_ai_stage;
#ifdef A6_AUDIO_TONE
static bool a6_at_codec;
static int a6_ac_cleanup;
static int a6_ac_feed(void);
static int a6_ac_execute_locked(bool playback);
#include "a6-audio-tone.inc"
#endif
static int a6_ai_result = -EAGAIN;
static void a6_af_read_amp(void)
{
	bool gate[2]={false,false}, clocks=false, reset=false, inherited_idle;
	unsigned int i;
	int ret=0;
	u32 v;
	a6_ai_stage=1;
	/* Caller holds the charger mutex throughout clock/reset/I2C/restore. */
	a6_af_i2c_snapshot(0);
	a6_ai_reset[0]=readl(a6_touch_gpio+42*4);
	if(!a6_power_is_idle(a6_af_i2c[0][0]) || a6_af_i2c[0][1]!=0 ||
	   a6_af_i2c[0][2]!=0x104 || a6_af_i2c[0][3]!=1 || a6_af_i2c[0][4]!=0x2ff ||
	   a6_ai_reset[0]!=0x202) {ret=-EBUSY;goto out;}
	if(a6_memory_capture_copy[0]!=0x41364d31 || a6_memory_capture_copy[1]!=1 ||
	   a6_memory_capture_copy[7] || a6_memory_capture_copy[25]!=5 ||
	   a6_memory_capture_copy[480]!=3 || a6_memory_capture_copy[481]!=1 ||
	   (a6_memory_capture_copy[482]!=4 && a6_memory_capture_copy[482]!=8) ||
	   a6_memory_capture_copy[484] || a6_memory_capture_copy[485]!=1) {ret=-ENODATA;goto out;}
	a6_ai_fixed=a6_memory_capture_copy[483];
	if(a6_ai_fixed!=24000000) {ret=-ERANGE;goto out;}
	for(i=0;i<2;i++) {
		v=readl(a6_touch_pmgr+(i ? 0xac : 0xa0));a6_ai_gate[i][0]=v;
		if(v==U32_MAX || v!=readl(a6_touch_pmgr+(i ? 0xac : 0xa0)) ||
		   ((v&255)!=0 && (v&255)!=255)) {ret=-EBUSY;goto restore;}
	}
	for(i=0;i<2;i++) {
		if(!(a6_ai_gate[i][0]&255)) {
			gate[i]=true;writel(a6_ai_gate[i][0]|15,a6_touch_pmgr+(i ? 0xac : 0xa0));
			ret=a6_af_poll(a6_touch_pmgr+(i ? 0xac : 0xa0),255,255);if(ret)goto restore;
		}
		a6_ai_gate[i][1]=readl(a6_touch_pmgr+(i ? 0xac : 0xa0));
	}
	a6_ai_stage=2;
	for(i=0;i<3;i++) {
		a6_ai_regs[0][i]=readl(a6_ai_iis+(i==0 ? 0 : i==1 ? 8 : 0x34));
		a6_ai_nc[0][i]=readl(a6_af_nco+0x2d0+4*i);
	}
	a6_ai_acs[0]=readl(a6_af_acs+0x18);
	a6_ai_route[0]=readl(a6_ai_switch+0x48);
	/* Measured cold-boot tuple: stream-control enable bits6 are clear.
	 * Stock811a5054 builds01f80006; MCLK-only811a4ba0/2 clears both.
	 * Admit this exact tuple, not arbitrary nonzero stream controls. */
	inherited_idle=a6_ai_regs[0][0]==0x22 && a6_ai_regs[0][1]==0x01f80000 && a6_ai_regs[0][2]==0x01f80000;
	if((!inherited_idle && ((a6_ai_regs[0][0]!=0 && a6_ai_regs[0][0]!=0x34 && a6_ai_regs[0][0]!=0x36) ||
	   a6_ai_regs[0][1] || a6_ai_regs[0][2])) || a6_ai_acs[0]>1 ||
	   a6_ai_route[0]==U32_MAX || (a6_ai_route[0]&1) ||
	   a6_ai_nc[0][0]!=0x80010000 || a6_ai_nc[0][1] || a6_ai_nc[0][2]) {ret=-EBUSY;goto restore;}
	clocks=true;
	writel(0,a6_af_acs+0x18);
	writel(0,a6_ai_iis+8);writel(0,a6_ai_iis+0x34);
	writel(0x134,a6_ai_iis);
	ret=a6_af_poll(a6_ai_iis,2,2);if(ret)goto restore;
	writel(a6_ai_route[0]|1,a6_ai_switch+0x48);
	a6_ai_acs[1]=readl(a6_af_acs+0x18);
	a6_ai_route[1]=readl(a6_ai_switch+0x48);
	for(i=0;i<3;i++)a6_ai_regs[1][i]=readl(a6_ai_iis+(i==0 ? 0 : i==1 ? 8 : 0x34));
	if(a6_ai_regs[1][0]!=0x136 || a6_ai_regs[1][1] || a6_ai_regs[1][2] ||
	   a6_ai_acs[1] || a6_ai_route[1]!=(a6_ai_route[0]|1)) {ret=-EIO;goto restore;}
	a6_ai_stage=3;
	usleep_range(10000,11000); /* Stock reset assertion settling, no release pulse yet. */
	reset=true;writel(a6_ai_reset[0]|1,a6_touch_gpio+42*4);
	a6_ai_reset[1]=readl(a6_touch_gpio+42*4);
	if(a6_ai_reset[1]!=(a6_ai_reset[0]|1)) {ret=-EIO;goto restore;}
	usleep_range(1000,2000); /* Stock reset release settling. */
	a6_ai_stage=4;
	a6_af_read_amp_locked();ret=a6_af_amp;
#ifdef A6_AUDIO_TONE
	if(!ret && a6_at_requested)ret=a6_at_play();
#endif
restore:
	/* Hold reset before disconnecting MCLK, including NACK/timeout paths. */
	if(reset) {
		writel(a6_ai_reset[0],a6_touch_gpio+42*4);
		a6_ai_reset[2]=readl(a6_touch_gpio+42*4);
		if(a6_ai_reset[2]!=a6_ai_reset[0])a6_af_cleanup=-EUCLEAN;
		usleep_range(1000,2000);
	}
	if(clocks) {
		writel(a6_ai_route[0],a6_ai_switch+0x48);
		writel(a6_ai_regs[0][0],a6_ai_iis);
		if(a6_af_poll(a6_ai_iis,U32_MAX,a6_ai_regs[0][0]))a6_af_cleanup=-EUCLEAN;
		writel(a6_ai_regs[0][1],a6_ai_iis+8);writel(a6_ai_regs[0][2],a6_ai_iis+0x34);
		writel(a6_ai_acs[0],a6_af_acs+0x18);
		for(i=0;i<3;i++) {
			a6_ai_regs[2][i]=readl(a6_ai_iis+(i==0 ? 0 : i==1 ? 8 : 0x34));
			a6_ai_nc[1][i]=readl(a6_af_nco+0x2d0+4*i);
			if(a6_ai_regs[2][i]!=a6_ai_regs[0][i] || a6_ai_nc[1][i]!=a6_ai_nc[0][i])a6_af_cleanup=-EUCLEAN;
		}
		a6_ai_route[2]=readl(a6_ai_switch+0x48);a6_ai_acs[2]=readl(a6_af_acs+0x18);
		if(a6_ai_route[2]!=a6_ai_route[0] || a6_ai_acs[2]!=a6_ai_acs[0])a6_af_cleanup=-EUCLEAN;
	}
	for(i=2;i-->0;) {
		if(gate[i]) {
			writel(a6_ai_gate[i][0],a6_touch_pmgr+(i ? 0xac : 0xa0));
			if(a6_af_poll(a6_touch_pmgr+(i ? 0xac : 0xa0),255,a6_ai_gate[i][0]&255))a6_af_cleanup=-EUCLEAN;
		}
		a6_ai_gate[i][2]=readl(a6_touch_pmgr+(i ? 0xac : 0xa0));
		if(gate[i] && a6_ai_gate[i][2]!=a6_ai_gate[i][0])a6_af_cleanup=-EUCLEAN;
	}
out:
	a6_ai_result=ret;a6_af_amp=ret;
}
#else
static void a6_af_read_amp(void) {a6_af_read_amp_locked();}
#endif

static ssize_t a6_af_run(struct kobject *k, struct kobj_attribute *a, const char *buf, size_t count)
{
	bool gates[2] = {false,false}, nco = false, acs = false, controller = false;
	unsigned int i, j, burst, tries;
	const unsigned int sizes[] = {32,64,160};
	#ifdef A6_AUDIO_TONE
	/* Stock layout0 with DT speaker eight16-bit slots, DAC slot0 only.
	 * 810bfbfc requests12.288MHz; writes control0f107005 and TX mask1. */
	u32 config[] = {0x1010,0x0f107005,1,0,0x208,0x0d,0x007f0004,1,0x10a,0x0d,0x007f0004,6};
	const u32 serial_clock=12288000;
#else
	const u32 config[] = {0x1010,0x0f101005,1,0,0x208,0x0d,0x007f0004,3,0x10a,0x0d,0x007f0004,0};
	const u32 serial_clock=3072000;
#endif
	u32 v, control;
	int ret = 0;

#ifdef A6_AUDIO_ALSA
 return -EOPNOTSUPP; /* ALSA owns this candidate; diagnostic writes are disabled. */
#endif
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	#ifdef A6_AUDIO_TONE
	unsigned int variant=0,level=0,gpio_state=0,all_slots=0,ios_burst=0;
	static const unsigned int peaks[]={3277,8231,16422,23197,32767};
	bool ios_state=sscanf(buf,"stock-speaker44-ios-%u",&ios_burst)==1;
	if(ios_state && (ios_burst<1 || ios_burst>2))return -EINVAL;
	bool sweep44=sscanf(buf,"stock-speaker44-sweep-%u-allslots-%u",&gpio_state,&all_slots)==2;
	if(sweep44 && (gpio_state>3 || all_slots>1))return -EINVAL;
	bool stock44100=ios_state || sweep44 || sscanf(buf,"stock-speaker44-level-%u",&level)==1;
	if(sweep44 || ios_state)level=4;
	if(stock44100 && level>=ARRAY_SIZE(peaks))return -EINVAL;
	bool ladder=sscanf(buf,"codec-amp-level-%u-variant-%u",&level,&variant)==2;
	if(ladder && (level>=ARRAY_SIZE(peaks) || variant>7))return -EINVAL;
	bool supplies=sscanf(buf,"audio-supply-probe-%u",&variant)==1;
	bool reference=ladder || sscanf(buf,"codec-amp-variant-%u",&variant)==1;
	if(reference && variant>7)return -EINVAL;
	bool codec=sysfs_streq(buf,"codec-receiver-enable-restore");
	bool probe=supplies || sscanf(buf,"audio-probe-%u",&variant)==1;
	if(probe && variant!=0 && variant!=4)return -EINVAL;
	if (!stock44100 && !reference && !codec && !probe && !sysfs_streq(buf,"quiet-tone-enable-restore") &&
	    (sscanf(buf,"audio-variant-%u",&variant)!=1 || variant>7))return -EINVAL;
	a6_at_requested=true;
#else
	if (!sysfs_streq(buf,"silent-fifo-enable-restore")) return -EINVAL;
#endif
	for (tries=0; tries<100; tries++) {
		if (mutex_trylock(&a6_touch_lock)) break;
		usleep_range(1000,2000);
	}
	if (tries == 100) return -EBUSY;
	#ifdef A6_AUDIO_TONE
	/* Explicit calls may repeat after verified rollback. Never carry cached
	 * samples, ADC readings or snapshots into the next bounded run. */
	if (a6_af_attempted && a6_af_cleanup) {ret=-EUCLEAN;goto unlock;}
	a6_at_reset_run();a6_at_codec=codec || reference;a6_at_reference=reference;a6_at_variant=variant;a6_at_peak=ladder ? peaks[level] : (probe || reference ? 512 : 32);a6_at_supplies=supplies;
	if(stock44100){a6_at_stock44100=true;a6_at_frame_limit=44100;a6_at_variant=4|gpio_state;a6_at_peak=peaks[level];variant=a6_at_variant;a6_at_all_slots=all_slots;a6_at_ios_route=ios_state;a6_at_ios_amp=ios_state && ios_burst==2;if(a6_at_ios_amp)a6_at_frame_limit=48000;}
	if(supplies)config[11]=0x1e;
	if(codec || reference)memcpy(config,a6_ac_mca_config,sizeof(config));
	if(reference){config[10]=0x007f0004;config[11]=6;}
	if(variant&4){config[1]=0x0f107000;config[4]=0x108;config[10]=0x007f0004;}
	if(stock44100){const u32 stock[]={0x1010,0x0f107000,1,0,0x108,0xd,0x00170004,1,0x10a,0xd,0x002b0004,3};memcpy(config,stock,sizeof(stock));if(ios_state)config[10]=0x002f0004;if(all_slots){config[6]=0x007b0004;config[7]=255;}}
	a6_af_snaps=a6_af_written=a6_af_source=a6_af_nsteps=0;
	a6_af_polls=a6_af_peak=0;a6_af_result=a6_af_cleanup=0;
	a6_af_amp=-EAGAIN;a6_af_amp_id=0;a6_ai_stage=0;a6_ai_result=-EAGAIN;
	memset(a6_af_dump,0,sizeof(a6_af_dump));
	memset(a6_af_ntrace,0,sizeof(a6_af_ntrace));
	#else
	if (a6_af_attempted) { ret=-EALREADY; goto unlock; }
	#endif
	a6_af_attempted=true;
	for (i=0; i<2; i++) {
		v=readl(a6_touch_pmgr+(i ? 0xe0 : 0xa0)); a6_af_gate[i][0]=v;
		if (v == U32_MAX || v != readl(a6_touch_pmgr+(i ? 0xe0 : 0xa0)) ||
		    ((v & 255) != 0 && (v & 255) != 255)) { ret=-EBUSY; goto restore; }
	}
	for (i=0; i<2; i++) {
		if (!(a6_af_gate[i][0]&255)) {
			gates[i]=true; writel(a6_af_gate[i][0]|15,a6_touch_pmgr+(i ? 0xe0 : 0xa0));
			ret=a6_af_poll(a6_touch_pmgr+(i ? 0xe0 : 0xa0),255,255);
			if (ret) goto restore;
		}
		a6_af_gate[i][1]=readl(a6_touch_pmgr+(i ? 0xe0 : 0xa0));
	}
	a6_af_snapshot(0);
	/* No inherited active stream, DMA request, reset or sticky TX fault. */
	if ((readl(a6_af_mca+12)&2) || (readl(a6_af_mca+24)&1) ||
	    (readl(a6_af_mca+44)&1) || readl(a6_af_mca+0x44) ||
	    (readl(a6_af_mca+0x40)&0x3000) || readl(a6_af_mca+4)!=0x00800080) {
		ret=-EBUSY; goto restore;
	}
	for (i=0;i<ARRAY_SIZE(a6_af_offsets);i++) a6_af_saved[i]=readl(a6_af_mca+a6_af_offsets[i]);
	/* PMGR clock-ids[0]=324. AppleARMIODevice 8059a048 forwards to
	 * AppleS5L8950X 8114ca9c; ID>=256 selects clock-frequencies[ID-256].
	 * Startup 8114c5c4..5d8 copies that populated boot table into its cache.
	 * CPU fixed-frequency is a different clock. */
	if (a6_memory_capture_copy[0] != 0x41364d31 ||
	    a6_memory_capture_copy[1] != 1 || a6_memory_capture_copy[7] ||
	    a6_memory_capture_copy[25] != 5 || a6_memory_capture_copy[26] != 1 ||
	    a6_memory_capture_copy[27] != 1 || a6_memory_capture_copy[28] != 384) {
		ret=-ENODATA;goto restore;
	}
	a6_af_source=a6_memory_capture_copy[0x600/4 + 324-256];
	if(a6_af_source<1000000 || a6_af_source>2000000000) {ret=-ENODATA;goto restore;}
	/* Shared source clock can be recovered from stock NCO add/sub operands.
	 * Require all configured, valid existing channels to agree. Never guess from DT zeros. */
	for (i=0;i<7;i++) {
		for (j=0;j<3;j++) a6_af_ncos[i][j]=readl(a6_af_nco+0x2b0+16*i+4*j);
		v=a6_af_ncos[i][1]-a6_af_ncos[i][2];
		if ((a6_af_ncos[i][0]&0xc0000002)==0x80000000 && v>=1000000 && v<=2000000000) {
			if (a6_af_source && a6_af_source!=v) {ret=-EINVAL;goto restore;}
			a6_af_source=v;
		}
	}
	if (!a6_af_source) {ret=-ENODATA;goto restore;}
	control=a6_af_ncos[6][0];
	if (control==U32_MAX || (control&0x40000002)) {ret=-EBUSY;goto restore;}
	a6_af_acs_before=readl(a6_af_acs+0x24);
	if (a6_af_acs_before>1) {ret=-EINVAL;goto restore;}
	#ifdef A6_AUDIO_TONE
	if(!stock44100) {
	#endif
	nco=true;
	ret=a6_af_nwrite(0,0x82000000); if(ret) goto restore;
	ret=a6_af_nwrite(0,0x92000000); if(ret) goto restore;
	/* Stock8114e1fa doubles requested Hz;8114e1fe subtracts source. */
	ret=a6_af_nwrite(4,2*serial_clock); if(ret) goto restore;
	ret=a6_af_nwrite(8,2*serial_clock-a6_af_source); if(ret) goto restore;
	ret=a6_af_nwrite(0,0x92000400); if(ret) goto restore;
	ret=a6_af_nwrite(0,0x92000c00); if(ret) goto restore;
	ret=a6_af_nwrite(0,0x92000800); if(ret) goto restore;
	#ifdef A6_AUDIO_TONE
	}
	#endif
	acs=true; writel(0,a6_af_acs+0x24);
	if(readl(a6_af_acs+0x24)!=0) {ret=-EIO;goto restore;}
	controller=true; writel(0x301,a6_af_mca+0x44);
	ret=a6_af_poll(a6_af_mca+0x44,U32_MAX,0); if(ret) goto restore;
	for(i=0;i<ARRAY_SIZE(a6_af_offsets);i++) {
		writel(config[i],a6_af_mca+a6_af_offsets[i]);
		if(readl(a6_af_mca+a6_af_offsets[i])!=config[i]) {ret=-EIO;goto restore;}
	}
	a6_af_snapshot(1); /* configured, stopped */
	writel(config[4]|1,a6_af_mca+24); writel(config[1]|2,a6_af_mca+12);
	a6_af_snapshot(2); /* enabled */
#ifdef A6_AUDIO_TONE
	if(codec || reference){ret=a6_ac_execute_locked(true);a6_at_error=ret;if(a6_ac_cleanup)a6_af_cleanup=a6_ac_cleanup;}
	else {a6_af_read_amp();ret=a6_ai_result;}
	goto restore;
#endif
	udelay(1000); a6_af_snapshot(3); /* empty underrun */
	for(burst=0;burst<ARRAY_SIZE(sizes);burst++) {
		a6_af_fault[burst][0]=readl(a6_af_mca+0x40);
		/* Faults may be sticky: retain raw state then acknowledge only new TX faults. */
		if(burst) writel(a6_af_fault[burst][0]&0x3000,a6_af_mca+0x40);
		for(j=0;j<sizes[burst];j++) {
			/* Empirical layout0 status low byte is TX occupancy (0..128).
			 * Leave16 words of headroom; no DMA or competing producer enabled.
			 * One shared100-ms budget across the entire256-word diagnostic. */
			for (;;) {
				v=readl(a6_af_mca+0x40);
				if(v==U32_MAX || (v&0x2000) || (v&255)>128) {ret=-EIO;goto restore;}
				a6_af_peak=max(a6_af_peak,v&255);
				if((v&255)<112) break;
				if(a6_af_polls++>=10000) {ret=-ETIMEDOUT;goto restore;}
				udelay(10);
			}
			writel(0,a6_af_mca+0x28); a6_af_written++;
			/* 16-word bursts, 100us gaps; 160 cumulative words exceed capacity. */
			if((j&15)==15) {
				v=readl(a6_af_mca+0x40);
				a6_af_fault[burst][3]|=v;
				if(j==15) {
					a6_af_fault[burst][4]=v;
					if(!burst) writel(v&0x3000,a6_af_mca+0x40);
				}
				if(j+1<sizes[burst]) udelay(100);
			}
		}
		a6_af_fault[burst][1]=readl(a6_af_mca+0x40); a6_af_snapshot(4+2*burst);
		if(a6_af_fault[burst][1]&0x2000) {ret=-EOVERFLOW;goto restore;}
		udelay(1000);
		a6_af_fault[burst][2]=readl(a6_af_mca+0x40); a6_af_snapshot(5+2*burst);
	}
restore:
	if(controller) {
		writel(0,a6_af_mca+24); writel(0,a6_af_mca+44); writel(0x300,a6_af_mca+0x44);
		if(a6_af_poll(a6_af_mca+0x44,0x300,0)) a6_af_cleanup=-EUCLEAN;
		writel(a6_af_saved[1]&~2,a6_af_mca+12);
		/* Flush our zero-only FIFO before restoring inactive inherited configuration. */
		writel(0x301,a6_af_mca+0x44);
		if(a6_af_poll(a6_af_mca+0x44,U32_MAX,0)) a6_af_cleanup=-EUCLEAN;
		writel(readl(a6_af_mca+0x40)&0x30003000,a6_af_mca+0x40);
		for(i=ARRAY_SIZE(a6_af_offsets);i-->0;) writel(a6_af_saved[i],a6_af_mca+a6_af_offsets[i]);
		for(i=0;i<ARRAY_SIZE(a6_af_offsets);i++) {
			a6_af_restored[i]=readl(a6_af_mca+a6_af_offsets[i]);
			if(a6_af_restored[i]!=a6_af_saved[i]) a6_af_cleanup=-EUCLEAN;
		}
		a6_af_snapshot(10);
	}
	if(acs) {
		writel(a6_af_acs_before,a6_af_acs+0x24);
		a6_af_acs_after=readl(a6_af_acs+0x24);
		if(a6_af_acs_after!=a6_af_acs_before) a6_af_cleanup=-EUCLEAN;
	}
	if(nco) {
		if(a6_af_nwrite(0,0x82000000)) a6_af_cleanup=-EUCLEAN;
		for(i=1;i<3;i++) if(a6_af_nwrite(i*4,a6_af_ncos[6][i])) a6_af_cleanup=-EUCLEAN;
		if(a6_af_nwrite(0,a6_af_ncos[6][0])) a6_af_cleanup=-EUCLEAN;
		for(i=0;i<3;i++) {
			a6_af_nc_after[i]=readl(a6_af_nco+0x310+i*4);
			if(a6_af_nc_after[i]!=a6_af_ncos[6][i]) a6_af_cleanup=-EUCLEAN;
		}
	}
	for(i=2;i-->0;) {
		if(gates[i]) {
			writel(a6_af_gate[i][0],a6_touch_pmgr+(i ? 0xe0 : 0xa0));
			if(a6_af_poll(a6_touch_pmgr+(i ? 0xe0 : 0xa0),255,a6_af_gate[i][0]&255)) a6_af_cleanup=-EUCLEAN;
		}
		a6_af_gate[i][2]=readl(a6_touch_pmgr+(i ? 0xe0 : 0xa0));
		if(gates[i] && a6_af_gate[i][2]!=a6_af_gate[i][0]) a6_af_cleanup=-EUCLEAN;
	}
	/* Amp observation is independent of FIFO experiment failure, after serial cleanup. */
	#ifndef A6_AUDIO_TONE
	if(!a6_af_cleanup) a6_af_read_amp();
#endif
	a6_af_result=ret;
	if(a6_af_cleanup) ret=a6_af_cleanup;
unlock:
	mutex_unlock(&a6_touch_lock); return ret ? ret : count;
}
static ssize_t a6_af_status(struct kobject *k, struct kobj_attribute *a, char *buf)
{
	ssize_t n; unsigned int i;
	if(!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n=sysfs_emit(buf,"A6_AUDIO_FIFO_DISCOVER_V2\nattempted=%u result=%d cleanup=%d snapshots=%u writes=%u source_hz=%u amp_result=%d amp_id=%02x gpio42=%08x\n",a6_af_attempted,a6_af_result,a6_af_cleanup,a6_af_snaps,a6_af_written,a6_af_source,a6_af_amp,a6_af_amp_id,a6_af_gpio);
	n+=sysfs_emit_at(buf,n,"pacing_polls=%u peak_before_write=%u\nsnapshot_ids=",a6_af_polls,a6_af_peak);
	for(i=0;i<a6_af_snaps;i++) n+=sysfs_emit_at(buf,n,"%s%u",i ? "," : "",a6_af_stage[i]);
	n+=sysfs_emit_at(buf,n,"\n");
	for(i=0;i<a6_af_nsteps && i<ARRAY_SIZE(a6_af_ntrace);i++) n+=sysfs_emit_at(buf,n,"nco_write=%02x,%08x,%08x,%08x\n",a6_af_ntrace[i][0],a6_af_ntrace[i][1],a6_af_ntrace[i][2],a6_af_ntrace[i][3]);
	for(i=0;i<2;i++) n+=sysfs_emit_at(buf,n,"gate%u=%08x/%08x/%08x\n",i,a6_af_gate[i][0],a6_af_gate[i][1],a6_af_gate[i][2]);
	n+=sysfs_emit_at(buf,n,"acs=%08x/%08x\n",a6_af_acs_before,a6_af_acs_after);
	for(i=0;i<7;i++) n+=sysfs_emit_at(buf,n,"nco%u=%08x,%08x,%08x,%08x\n",i,a6_af_ncos[i][0],a6_af_ncos[i][1],a6_af_ncos[i][2],a6_af_ncos[i][3]);
	n+=sysfs_emit_at(buf,n,"nco6_restored=%08x,%08x,%08x,%08x\n",a6_af_nc_after[0],a6_af_nc_after[1],a6_af_nc_after[2],a6_af_nc_after[3]);
	for(i=0;i<3;i++) n+=sysfs_emit_at(buf,n,"burst%u_fault=%08x/%08x/%08x/%08x/%08x\n",i,a6_af_fault[i][0],a6_af_fault[i][1],a6_af_fault[i][2],a6_af_fault[i][3],a6_af_fault[i][4]);
	for(i=0;i<ARRAY_SIZE(a6_af_offsets);i++) n+=sysfs_emit_at(buf,n,"restore_%03x=%08x/%08x\n",a6_af_offsets[i],a6_af_saved[i],a6_af_restored[i]);
	for(i=0;i<2;i++) n+=sysfs_emit_at(buf,n,"i2c%u=%08x,%08x,%08x,%08x,%08x\n",i,a6_af_i2c[i][0],a6_af_i2c[i][1],a6_af_i2c[i][2],a6_af_i2c[i][3],a6_af_i2c[i][4]);
	#ifdef A6_AUDIO_AMP_ID
 n+=sysfs_emit_at(buf,n,"amp_stage=%u amp_stage_result=%d mclk_source_hz=%u\n",a6_ai_stage,a6_ai_result,a6_ai_fixed);
 for(i=0;i<2;i++)n+=sysfs_emit_at(buf,n,"amp_gate%u=%08x/%08x/%08x\n",i,a6_ai_gate[i][0],a6_ai_gate[i][1],a6_ai_gate[i][2]);
 for(i=0;i<3;i++)n+=sysfs_emit_at(buf,n,"amp_iis%u=%08x,%08x,%08x\n",i,a6_ai_regs[i][0],a6_ai_regs[i][1],a6_ai_regs[i][2]);
 n+=sysfs_emit_at(buf,n,"amp_acs=%08x/%08x/%08x amp_route48=%08x/%08x/%08x gpio42_stage=%08x/%08x/%08x\n",a6_ai_acs[0],a6_ai_acs[1],a6_ai_acs[2],a6_ai_route[0],a6_ai_route[1],a6_ai_route[2],a6_ai_reset[0],a6_ai_reset[1],a6_ai_reset[2]);
 for(i=0;i<2;i++)n+=sysfs_emit_at(buf,n,"amp_nco2_%u=%08x,%08x,%08x\n",i,a6_ai_nc[i][0],a6_ai_nc[i][1],a6_ai_nc[i][2]);
#endif
#ifdef A6_AUDIO_TONE
 n+=sysfs_emit_at(buf,n,"tone_error=%d samples=%u peak=%u duration_samples=%u voltage_mv=%u/%u/%u min_mv=%u watchdog=%u status=%08x/%08x calib_flags=%x drain_words_hz=%u tone_elapsed_us=%u\n",a6_at_error,a6_at_samples,a6_at_peak,a6_at_frame_limit,a6_at_mv[0],a6_at_mv[1],a6_at_mv[2],a6_at_min_mv,atomic_read(&a6_at_expired),a6_at_status_before,a6_at_status_after,a6_memory_capture_copy[513],a6_at_drain_hz,a6_at_elapsed_us);
 n+=sysfs_emit_at(buf,n,"ios_playback_route=%u ios_amp_overrides=%u rx_telemetry_disabled=%u\n",a6_at_ios_route,a6_at_ios_amp,a6_at_ios_route);
 n+=sysfs_emit_at(buf,n,"stock44100=%u all_slots=%u nominal_frame_hz=%u silent_drain_words=%u silent_drain_us=%u\n",a6_at_stock44100,a6_at_all_slots,a6_at_frame_limit,a6_at_silent_drain_words,a6_at_silent_drain_us);
 n+=sysfs_emit_at(buf,n,"fifo_max_service_gap_us=%llu\n",(unsigned long long)div_u64(a6_at_max_gap,1000));
 for(i=0;i<2;i++)n+=sysfs_emit_at(buf,n,"tone_route%u=%08x/%08x/%08x\n",i,a6_at_routes[i][0],a6_at_routes[i][1],a6_at_routes[i][2]);
 for(i=0;i<3;i++)n+=sysfs_emit_at(buf,n,"amp_fault%u=%02x,%02x,%02x,%02x\n",i,a6_at_faults[i][0],a6_at_faults[i][1],a6_at_faults[i][2],a6_at_faults[i][3]);
 n+=sysfs_emit_at(buf,n,"monitor_rx_count=%u nonzero=%u peak=%u status=%08x first=",a6_at_rx_count,a6_at_rx_nonzero,a6_at_rx_peak,a6_at_rx_status);
 for(i=0;i<16;i++)n+=sysfs_emit_at(buf,n,"%04x%s",a6_at_rx_first[i],i==15 ? "\n" : ",");
 n+=sysfs_emit_at(buf,n,"variant=%u supplies=%u monitor_counts=%u/%u/%u play_06_07_08_0d_0f_10_12=%02x,%02x,%02x,%02x,%02x,%02x,%02x\n",a6_at_variant,a6_at_supplies,a6_at_monitor_count[0],a6_at_monitor_count[1],a6_at_monitor_count[2],a6_at_play_state[0],a6_at_play_state[1],a6_at_play_state[2],a6_at_play_state[3],a6_at_play_state[4],a6_at_play_state[5],a6_at_play_state[6]);
 n+=sysfs_emit_at(buf,n,"monitor_phase=%u/%u/%u\n",a6_at_monitor_phase[0],a6_at_monitor_phase[1],a6_at_monitor_phase[2]);
 for(i=0;i<3;i++){unsigned int j;n+=sysfs_emit_at(buf,n,"amp_power_phase%u=",i);for(j=0;j<ARRAY_SIZE(a6_at_power_regs);j++)n+=sysfs_emit_at(buf,n,"%02x:%02x%s",a6_at_power_regs[j],a6_at_power_state[i][j],j+1==ARRAY_SIZE(a6_at_power_regs)?"\n":",");}
 for(i=0;i<2;i++)n+=sysfs_emit_at(buf,n,"ext_gpio%u=%08x/%08x/%08x observed=%08x\n",90+i,a6_at_ext[i][0],a6_at_ext[i][1],a6_at_ext[i][2],a6_at_ext_observed[i]);
 n+=sysfs_emit_at(buf,n,"amp_alive9=%08x/%08x/%08x edges=%u\n",a6_at_alive[0],a6_at_alive[1],a6_at_alive[2],a6_at_alive_edges);
#endif
 mutex_unlock(&a6_touch_lock);return n;
}
static ssize_t a6_af_dumps(struct file *f, struct kobject *k, const struct bin_attribute *a, char *buf, loff_t off, size_t count)
{
	size_t size; ssize_t ret=0;
	if(!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock); size=a6_af_snaps*0x1000;
	if(off>=0 && off<size) {count=min(count,size-(size_t)off);memcpy(buf,(char *)a6_af_dump+off,count);ret=count;}
	mutex_unlock(&a6_touch_lock);return ret;
}
#ifdef A6_AUDIO_TONE
#include "a6-audio-codec.inc"
#endif
static struct kobj_attribute a6_af_run_attr=__ATTR(run,0200,NULL,a6_af_run);
static struct kobj_attribute a6_af_status_attr=__ATTR(status,0400,a6_af_status,NULL);
static struct attribute *a6_af_attrs[]={&a6_af_run_attr.attr,&a6_af_status_attr.attr,
#ifdef A6_AUDIO_TONE
&a6_ac_run_attr.attr,&a6_ac_status_attr.attr,
#endif
NULL};
static struct bin_attribute a6_af_dump_attr={.attr={.name="dumps",.mode=0400},.size=A6_AF_SNAPS*0x1000,.read=a6_af_dumps};
#ifdef A6_AUDIO_TONE
static ssize_t a6_at_readbacks(struct file *f,struct kobject *k,const struct bin_attribute *a,char *buf,loff_t off,size_t count)
{
 ssize_t ret=0;size_t size;
 if(!capable(CAP_SYS_RAWIO))return -EPERM;
 mutex_lock(&a6_touch_lock);size=a6_at_count*4;
 if(off>=0 && off<size){count=min(count,size-(size_t)off);memcpy(buf,(char *)a6_at_log+off,count);ret=count;}
 mutex_unlock(&a6_touch_lock);return ret;
}
static struct bin_attribute a6_at_rb_attr={.attr={.name="amp_readbacks",.mode=0400},.size=128*4,.read=a6_at_readbacks};
static ssize_t a6_at_monitors(struct file *f,struct kobject *k,const struct bin_attribute *a,char *buf,loff_t off,size_t count)
{
 ssize_t ret=0;if(!capable(CAP_SYS_RAWIO))return -EPERM;
 mutex_lock(&a6_touch_lock);
 if(off>=0 && off<sizeof(a6_at_monitor)){count=min(count,sizeof(a6_at_monitor)-(size_t)off);memcpy(buf,(char *)a6_at_monitor+off,count);ret=count;}
 mutex_unlock(&a6_touch_lock);return ret;
}
static struct bin_attribute a6_at_mon_attr={.attr={.name="monitors",.mode=0400},.size=sizeof(a6_at_monitor),.read=a6_at_monitors};
static const struct bin_attribute *const a6_af_binattrs[]={&a6_af_dump_attr,&a6_at_rb_attr,&a6_at_mon_attr,&a6_ac_log_attr,NULL};
#else
static const struct bin_attribute *const a6_af_binattrs[]={&a6_af_dump_attr,NULL};
#endif
static const struct attribute_group a6_af_group={.name="a6_audio",.attrs=a6_af_attrs,.bin_attrs=a6_af_binattrs};
static int __init a6_af_init(void)
{
	int ret;
	if(!of_machine_is_compatible("apple,n42ap")||!a6_touch_pmgr||!a6_touch_i2c||!a6_touch_gpio) return -ENODEV;
	a6_af_mca=ioremap(0x34196000,0x1000); a6_af_nco=ioremap(0x3f100000,0x1000); a6_af_acs=ioremap(0x341a0000,0x1000);
	if(!a6_af_mca||!a6_af_nco||!a6_af_acs) {ret=-ENOMEM;goto fail;}
	#ifdef A6_AUDIO_AMP_ID
 a6_ai_iis=ioremap(0x34192000,0x1000);a6_ai_switch=ioremap(0x3fa01000,0x1000);
 if(!a6_ai_iis || !a6_ai_switch){ret=-ENOMEM;goto fail;}
#endif
#ifdef A6_AUDIO_TONE
 a6_ac_spi=ioremap(0x32300000,0x1000);a6_ac_iis=ioremap(0x34190000,0x1000);
 if(!a6_ac_spi || !a6_ac_iis){ret=-ENOMEM;goto fail;}
#endif
 ret=sysfs_create_group(firmware_kobj,&a6_af_group);if(!ret)return 0;
fail:
#ifdef A6_AUDIO_TONE
 if(a6_ac_spi)iounmap(a6_ac_spi);if(a6_ac_iis)iounmap(a6_ac_iis);
#endif
#ifdef A6_AUDIO_AMP_ID
 if(a6_ai_iis)iounmap(a6_ai_iis);if(a6_ai_switch)iounmap(a6_ai_switch);
#endif
 if(a6_af_mca)iounmap(a6_af_mca);if(a6_af_nco)iounmap(a6_af_nco);if(a6_af_acs)iounmap(a6_af_acs);return ret;
}
late_initcall(a6_af_init);

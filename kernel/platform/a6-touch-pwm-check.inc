// SPDX-License-Identifier: GPL-2.0-only
/* Included before CHECK. Fixed n42 channel2 trial, never a general PWM API.
 * Stock pwmC: default32768Hz, half duty, mode4003. Only live24MHz accepted.
 * Caller holds a6_touch_lock and restores the stopped channel on every path.
 */
#define A6_TOUCH_PWM_CHECK 1
#include <linux/delay.h>
static u32 a6_pwm_probe_hz, a6_pwm_probe_high, a6_pwm_probe_low;
static u32 a6_pwm_probe_first[3], a6_pwm_probe_later[3];
static bool a6_pwm_probe_written, a6_pwm_probe_readback, a6_pwm_probe_restored;

static int a6_pwm_probe_validate(void)
{
	const u32 *c = a6_memory_capture_copy;
	u32 gate, nonzero = 0;
	unsigned int i;
	const u8 *table = (const u8 *)c + 0x600;
	if (!a6_touch_pwm || c[0] != 0x41364d31 || c[1] != 1 ||
	    c[5] > 19 || c[7] || c[25] != 5 || c[26] != 1 ||
	    c[27] != 1 || c[28] != 384 || c[480] != 3 || c[481] != 1 ||
	    (c[482] != 4 && c[482] != 8) || c[483] != 24000000 ||
	    c[484] != 0 || c[485] != 1)
		return -EINVAL;
	for (i = 0; i < 384; i++)
		nonzero += table[i] != 0;
	if (nonzero != c[29])
		return -EINVAL;
	gate = readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE);
	if (gate == U32_MAX || (gate & 0xff) != 0xff ||
	    gate != readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE))
		return -EBUSY;
	if (readl(a6_touch_pwm + 0x10) || readl(a6_touch_pwm + 0x14) ||
	    readl(a6_touch_pwm + 0x20))
		return -EBUSY;
	a6_pwm_probe_hz = c[483];
	/* round(24000000/32768)=732; half duty gives366 high and366 low. */
	a6_pwm_probe_high = 366;
	a6_pwm_probe_low = 366;
	return 0;
}

static int a6_pwm_probe_start(void)
{
	a6_pwm_probe_written = true;
	writel(a6_pwm_probe_high, a6_touch_pwm + 0x10);
	writel(a6_pwm_probe_low, a6_touch_pwm + 0x14);
	writel(0x4003, a6_touch_pwm + 0x20);
	/* n42 live V2 trial: both snapshots retained366/366/4001 after
	 * stock4003 write. Require that exact observed state, not a bit mask.
	 * This establishes register acceptance, not a measured pin waveform.
	 */
	a6_pwm_probe_first[0] = readl(a6_touch_pwm + 0x10);
	a6_pwm_probe_first[1] = readl(a6_touch_pwm + 0x14);
	a6_pwm_probe_first[2] = readl(a6_touch_pwm + 0x20);
	udelay(10);
	a6_pwm_probe_later[0] = readl(a6_touch_pwm + 0x10);
	a6_pwm_probe_later[1] = readl(a6_touch_pwm + 0x14);
	a6_pwm_probe_later[2] = readl(a6_touch_pwm + 0x20);
	a6_pwm_probe_readback = a6_pwm_probe_first[0] == a6_pwm_probe_high &&
		a6_pwm_probe_first[1] == a6_pwm_probe_low &&
		a6_pwm_probe_first[2] == 0x4001 &&
		a6_pwm_probe_later[0] == a6_pwm_probe_high &&
		a6_pwm_probe_later[1] == a6_pwm_probe_low &&
		a6_pwm_probe_later[2] == 0x4001;
	return a6_pwm_probe_readback ? 0 : -EIO;
}

static bool a6_pwm_probe_restore(void)
{
	/* Reset is already asserted by CHECK cleanup before stopping PWM. */
	writel(0, a6_touch_pwm + 0x20);
	writel(0, a6_touch_pwm + 0x10);
	writel(0, a6_touch_pwm + 0x14);
	a6_pwm_probe_restored = !readl(a6_touch_pwm + 0x10) &&
		!readl(a6_touch_pwm + 0x14) && !readl(a6_touch_pwm + 0x20);
	return a6_pwm_probe_restored;
}

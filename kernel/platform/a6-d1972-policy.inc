// SPDX-License-Identifier: GPL-2.0-only
/* N42 USB 500 mA-class charger policy. Nothing charges until root writes a
 * control command. Two modes share the same guards and PMU programming:
 *
 * - Manual leases: "arm-500-class-10m-after-tbat-check" and up to two
 *   "rearm-..." renewals, ten minutes each, as in the attended trials.
 * - Automatic ("auto"): charge while a source is attached, stop at the VBAT
 *   ceiling or outside the TBAT window, resume below the hysteresis point,
 *   and clear the input limit on detach. "pause" stops charging but keeps
 *   the input supply; "auto" resumes; "disarm" leaves automatic mode.
 *
 * Every two seconds while charging: VBUS in range, VBAT <= 4250 mV,
 * candidate TBAT 10..35 C (the calibration read ~5 C below iOS, so 35 keeps
 * the real cell under ~40 C), and PMU readback unchanged. A readback
 * mismatch latches a fault that stops automatic charging until "auto".
 * The 500 mA charge request is a candidate, not a recovered iOS value.
 * No power_supply CHARGING status is inferred from these settings.
 */
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/reboot.h>
#define A6_POLICY_INPUT 16 /* Stock +0x7c floors 500 / 30 to 480 mA. */
#define A6_POLICY_TARGET 43 /* Stock +0x68: (500 - 70) / 10, absent adjustment. */
#define A6_POLICY_VBAT_MIN 3200
#define A6_POLICY_VBAT_MAX 4250
#define A6_POLICY_TBAT_MIN 10
#define A6_POLICY_TBAT_MAX 35
#define A6_AUTO_TBAT_RESUME 32
#define A6_AUTO_RESUME_MV 4100
#define A6_AUTO_REARM_GAP (120 * HZ)
#define A6_POLICY_SAMPLES 128
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
#define A6_LOW_VBAT_MV 3600
#define A6_LOW_PLUGGED_CRITICAL_MV 3400
#define A6_LOW_VBUS_MV 500
#define A6_LOW_STREAK_SAMPLES 16 /* Thirty seconds between first and last. */
static struct delayed_work a6_low_work;
static bool a6_low_enabled, a6_low_triggered;
static bool a6_low_attended_trial, a6_low_attended_plugged;
static bool a6_low_plugged, a6_low_streak_plugged;
static unsigned int a6_low_streak, a6_low_samples;
static unsigned int a6_low_vbus_mv, a6_low_vbat_mv;
static int a6_low_result;
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
static bool a6_low_screen_ok;
static unsigned int a6_low_b0, a6_low_off;
static int a6_low_reg_result;
static bool a6_low_screen_failure;
static unsigned int a6_low_screen_stage;
static int a6_low_screen_stock_result;
static const u8 a6_low_hex_font[16][7] = {
	{14,17,19,21,25,17,14}, {4,12,4,4,4,4,14},
	{14,17,1,2,4,8,31}, {30,1,1,14,1,1,30},
	{2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
	{14,17,17,14,17,17,14}, {31,1,2,4,8,8,8},
	{14,17,17,15,1,1,14}, {30,17,17,15,1,1,30},
	{31,17,17,31,17,17,17}, {30,17,17,30,17,17,30},
	{14,17,16,16,16,17,14}, {30,17,17,17,17,17,30},
	{31,16,16,30,16,16,16}, {31,16,16,30,16,16,16},
};

static void a6_low_screen_digit(unsigned int x, unsigned int y, u8 digit)
{
	u32 __iomem *fb = (u32 __iomem *)(unsigned long)0xbf7aa000;
	unsigned int row, col, dx, dy;

	for (row = 0; row < 7; row++)
		for (col = 0; col < 5; col++) {
			u32 color = a6_low_hex_font[digit & 15][row] &
				BIT(4 - col) ? 0x00ffffff : 0;
			for (dy = 0; dy < 2; dy++)
				for (dx = 0; dx < 2; dx++)
					writel(color, fb +
						(y + row * 2 + dy) * 640 +
						(x + col * 2 + dx));
		}
}

static void a6_low_screen_draw(void)
{
	static const unsigned int rows = 8;
	u32 values[8] = {
		a6_low_screen_failure ? 0xa6f00000 | a6_low_screen_stage :
			a6_low_samples,
		a6_low_vbus_mv, a6_low_vbat_mv,
		a6_low_b0, a6_low_off,
		a6_low_screen_failure ? (u32)a6_low_screen_stock_result :
			(u32)a6_low_reg_result,
		a6_low_streak, a6_low_triggered,
	};
	u32 __iomem *fb = (u32 __iomem *)(unsigned long)0xbf7aa000;
	unsigned int row, x;

	if (!a6_low_screen_ok)
		return;
	for (row = 0; row < rows; row++) {
		unsigned int y = 855 + row * 29;
		for (x = 0; x < 21; x++)
			memset_io(fb + (y + x) * 640 + 410, 0, 180 * 4);
		a6_low_screen_digit(410, y, row);
		for (x = 0; x < 8; x++)
			a6_low_screen_digit(434 + x * 14, y,
				(values[row] >> (28 - x * 4)) & 15);
	}
}
#endif
#endif
static struct delayed_work a6_policy_work;
static bool a6_policy_active, a6_policy_stopping, a6_policy_ever_armed;
static bool a6_policy_clean_stop_seen;
static bool a6_policy_keep_input, a6_policy_leased;
static unsigned int a6_policy_arm_count;
static int a6_policy_result, a6_policy_disable_result;
static unsigned long a6_policy_deadline;
static unsigned int a6_policy_vbus_mv, a6_policy_vbat_mv;
static int a6_policy_tbat_c;
static u8 a6_policy_initial[5], a6_policy_live[5];
static u8 a6_policy_fault_live[5];
static bool a6_policy_fault_live_valid;
static bool a6_auto_enabled, a6_auto_paused, a6_auto_fault;
static bool a6_auto_attached, a6_auto_held, a6_auto_thermal_hold;
static unsigned int a6_auto_flip, a6_auto_arms;
static unsigned long a6_auto_last_stop;
static struct {
	unsigned long when;
	u16 vbus_mv, vbat_mv;
	s16 tbat_c;
	char state;
} a6_policy_samples[A6_POLICY_SAMPLES];
static unsigned int a6_policy_sample_count;
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
static bool a6_stock_off_armed;
static unsigned int a6_stock_off_stage;
static int a6_stock_off_result;
#endif

static int a6_policy_reg(u8 reg, u8 *val, bool write)
{
	return a6_power_xfer(reg, val, write, false);
}

static int a6_policy_snapshot(u8 *dst)
{
	static const u8 regs[] = { 0x1b, 0x3f, 0x43, 0x45, 0x46 };
	unsigned int i;
	int ret;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_policy_reg(regs[i], &dst[i], false);
		if (ret) return ret;
	}
	return 0;
}

/* One conversion with selector restoration even if the transaction fails. */
static int a6_policy_adc(u8 channel, unsigned int *raw)
{
	u8 before, control, lo, hi, verify;
	int ret, cr;
	ret = a6_vbus_xfer(0x48, &before, false);
	if (ret) return ret;
	if (before & 0x60) return -EBUSY;
	control = (before & 0x80) | 0x20 | channel;
	ret = a6_vbus_xfer(0x48, &control, true);
	if (!ret) {
		msleep(10);
		ret = a6_vbus_xfer(0x49, &lo, false);
		if (!ret) ret = a6_vbus_xfer(0x4a, &hi, false);
		if (!ret) *raw = (lo & 0x0f) | (hi << 4);
	}
	a6_power_recover();
	cr = a6_vbus_xfer(0x48, &before, true);
	if (cr && !ret) ret = cr;
	a6_power_recover();
	cr = a6_vbus_xfer(0x48, &verify, false);
	if (cr && !ret) ret = cr;
	if (!ret && verify != before) ret = -EUCLEAN;
	return ret;
}

/* Sample VBUS, VBAT and TBAT; returns only transaction errors. */
static int a6_policy_measure(void)
{
	unsigned int raw;
	int ret;
	ret = a6_power_validate();
	if (ret) return ret;
	ret = a6_policy_adc(15, &raw);
	if (ret) return ret;
	a6_policy_vbus_mv = (u32)((u64)raw * 88000 / 65536);
	ret = a6_policy_adc(4, &raw);
	if (ret) return ret;
	a6_policy_vbat_mv = 2500 + (u32)((u64)raw * 32000 / 65536);
	ret = a6_policy_adc(2, &raw);
	if (ret) return ret;
	a6_policy_tbat_c = a6_tbat_candidate_c(
		(u32)((u64)raw * 800000 / 65536));
	return 0;
}

#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
/* This worker runs independently of the charge policy, including when auto
 * is disabled. The sys-off callback cancels it before touching the PMU.
 */
static void a6_low_tick(struct work_struct *work)
{
	bool fire = false;
	bool plugged;
	bool mode_ok;
	int ret;

	mutex_lock(&a6_touch_lock);
	if (!a6_low_enabled || a6_low_triggered)
		goto out;
	ret = a6_policy_measure();
	a6_low_result = ret;
	a6_low_samples++;
	if (ret) {
		a6_low_streak = 0;
	} else {
		a6_low_vbus_mv = a6_policy_vbus_mv;
		a6_low_vbat_mv = a6_policy_vbat_mv;
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
		{
			u8 value;
			a6_low_reg_result = a6_policy_reg(0xb0, &value, false);
			if (!a6_low_reg_result)
				a6_low_b0 = value;
			if (!a6_low_reg_result) {
				a6_low_reg_result = a6_policy_reg(0x1b, &value,
								false);
				if (!a6_low_reg_result)
					a6_low_off = value;
			}
		}
#endif
		plugged = a6_low_vbus_mv >= A6_LOW_VBUS_MV;
		if (a6_low_attended_trial)
			mode_ok = a6_low_attended_plugged ?
				(plugged && !a6_policy_active) : !plugged;
		else
			/* A weak source or heavy load can drain an active charger. */
			mode_ok = true;
		if (a6_low_vbat_mv <=
		    (a6_low_attended_trial ? 4500 :
		     plugged ? A6_LOW_PLUGGED_CRITICAL_MV : A6_LOW_VBAT_MV) &&
		    mode_ok) {
			if (a6_low_streak && a6_low_streak_plugged == plugged)
				a6_low_streak++;
			else
				a6_low_streak = 1;
			a6_low_streak_plugged = plugged;
		} else {
			a6_low_streak = 0;
		}
	}
	if (a6_low_streak >= A6_LOW_STREAK_SAMPLES) {
		a6_low_triggered = true;
		a6_low_plugged = a6_low_streak_plugged;
		a6_stock_off_armed = !a6_low_plugged;
		fire = true;
	} else {
		schedule_delayed_work(&a6_low_work, 2 * HZ);
	}
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
	a6_low_screen_draw();
#endif
out:
	mutex_unlock(&a6_touch_lock);
	if (fire)
		__hw_protection_trigger(a6_low_plugged ?
					"a6 plugged low battery" :
					"a6 detached low battery",
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
					a6_low_attended_trial ? 30000 : 5000,
#else
					5000,
#endif
					HWPROT_ACT_SHUTDOWN);
}
#endif

static bool a6_policy_vbus_ok(void)
{
	return a6_policy_vbus_mv >= 4400 && a6_policy_vbus_mv <= 5500;
}

static bool a6_policy_cell_ok(void)
{
	return a6_policy_vbat_mv >= A6_POLICY_VBAT_MIN &&
	       a6_policy_vbat_mv <= A6_POLICY_VBAT_MAX &&
	       a6_policy_tbat_c >= A6_POLICY_TBAT_MIN &&
	       a6_policy_tbat_c <= A6_POLICY_TBAT_MAX;
}

static int a6_policy_check(void)
{
	int ret = a6_policy_measure();
	if (ret) return ret;
	if (!a6_policy_vbus_ok())
		return -ENOLINK;
	if (!a6_policy_cell_ok())
		return -ERANGE;
	return 0;
}

static bool a6_policy_live_charging(void)
{
	return !(a6_policy_live[0] & 4) &&
	       a6_policy_live[1] == A6_POLICY_TARGET &&
	       (a6_policy_live[2] & 0x3f) == A6_POLICY_INPUT &&
	       a6_policy_live[4] == a6_policy_initial[4];
}

/* 0x45 is reported state, not a programmed setpoint. Preserve all five
 * registers before rollback when a programmed-setpoint check fails. */
static void a6_policy_latch_fault_live(void)
{
	if (!a6_policy_fault_live_valid) {
		memcpy(a6_policy_fault_live, a6_policy_live,
		       sizeof(a6_policy_fault_live));
		a6_policy_fault_live_valid = true;
	}
}

/* Stop the charge request first. Keep the 480 mA USB system supply after
 * a guard stop or pause; clear it on detach or uncertain bus state.
 */
static int a6_policy_disable(bool keep_input)
{
	u8 v, expect;
	int ret, first = 0;
	if (!a6_policy_stopping)
		a6_policy_keep_input = keep_input;
	else
		keep_input = a6_policy_keep_input;
	a6_power_recover();
	ret = a6_policy_reg(0x1b, &v, false);
	if (ret) first = ret;
	else {
		v |= 4; /* Stock +0x68's below-70-mA mode. */
		ret = a6_policy_reg(0x1b, &v, true);
		if (ret && !first) first = ret;
	}
	a6_power_recover();
	v = 0;
	ret = a6_policy_reg(0x3f, &v, true);
	if (ret && !first) first = ret;
	a6_power_recover();
	v = keep_input ? A6_POLICY_INPUT : 0;
	ret = a6_policy_reg(0x43, &v, true);
	if (ret && !first) first = ret;
	a6_power_recover();
	ret = a6_policy_snapshot(a6_policy_live);
	if (ret && !first) first = ret;
	if (!first) {
		expect = a6_policy_live[0] & 4;
		if (!expect || a6_policy_live[1] ||
		    (a6_policy_live[2] & 0x3f) !=
			(keep_input ? A6_POLICY_INPUT : 0))
			first = -EUCLEAN;
	}
	a6_policy_disable_result = first;
	a6_policy_clean_stop_seen = !first;
	a6_policy_active = false;
	a6_policy_stopping = !!first;
	a6_auto_held = !first && keep_input;
	return first;
}

/* Program the charge request from a verified a6_policy_initial snapshot. */
static int a6_policy_program(bool leased)
{
	u8 v;
	int ret;
	a6_policy_ever_armed = true;
	v = A6_POLICY_INPUT;
	ret = a6_policy_reg(0x43, &v, true);
	if (ret) goto fail;
	v = a6_policy_initial[0] & ~4;
	ret = a6_policy_reg(0x1b, &v, true);
	if (ret) goto fail;
	v = A6_POLICY_TARGET;
	ret = a6_policy_reg(0x3f, &v, true);
	if (ret) goto fail;
	ret = a6_policy_snapshot(a6_policy_live);
	if (ret) goto fail;
	if (!a6_policy_live_charging()) {
		a6_policy_latch_fault_live();
		ret = -EUCLEAN;
		goto fail;
	}
	a6_policy_active = true;
	a6_auto_held = false;
	a6_policy_arm_count++;
	a6_policy_result = 0;
	a6_policy_keep_input = false;
	a6_policy_leased = leased;
	a6_policy_deadline = jiffies + 10 * 60 * HZ;
	return 0;
fail:
	a6_policy_result = ret;
	a6_policy_disable(false);
	return ret;
}

/* PMU states automatic mode may start from: the stock iBoot handoff, or
 * this driver's own verified stop (charge off, input 0 or 480 mA).
 */
static bool a6_auto_state_known(const u8 *s)
{
	if (s[4] != 0xa1)
		return false;
	if (!s[0] && s[1] == 3 && (s[2] & 0x3f) == 0x3f)
		return true;
	return s[0] == 4 && !s[1] &&
	       ((s[2] & 0x3f) == 0 || (s[2] & 0x3f) == A6_POLICY_INPUT);
}

static void a6_policy_record(char state)
{
	unsigned int i = a6_policy_sample_count++ % A6_POLICY_SAMPLES;
	a6_policy_samples[i].when = jiffies;
	a6_policy_samples[i].vbus_mv = a6_policy_vbus_mv;
	a6_policy_samples[i].vbat_mv = a6_policy_vbat_mv;
	a6_policy_samples[i].tbat_c = clamp(a6_policy_tbat_c, -999, 999);
	a6_policy_samples[i].state = state;
}

static void a6_auto_stop(int reason, bool keep_input)
{
	a6_policy_result = reason;
	a6_policy_disable(keep_input);
	a6_auto_last_stop = jiffies;
	if (reason == -ESTALE || a6_policy_disable_result)
		a6_auto_fault = true;
}

/* One automatic-mode step; caller holds a6_touch_lock. */
static void a6_auto_step(void)
{
	bool online;
	int ret;

	if (a6_policy_stopping) {
		a6_policy_disable(a6_policy_keep_input);
		a6_policy_record('S');
		return;
	}
	ret = a6_policy_measure();
	if (ret) {
		/* Monitoring lost: never keep charging without readings. */
		if (a6_policy_active)
			a6_auto_stop(ret, false);
		a6_policy_result = ret;
		a6_policy_record('E');
		return;
	}
	online = a6_policy_vbus_ok();
	if (online != a6_auto_attached) {
		if (++a6_auto_flip >= 2) {
			a6_auto_attached = online;
			a6_auto_flip = 0;
		}
	} else {
		a6_auto_flip = 0;
	}

	if (a6_policy_active) {
		if (!online) {
			a6_auto_stop(-ENOLINK, false);
		} else if (!a6_policy_cell_ok()) {
			if (a6_policy_tbat_c > A6_POLICY_TBAT_MAX)
				a6_auto_thermal_hold = true;
			a6_auto_stop(-ERANGE, true);
		} else {
			ret = a6_policy_snapshot(a6_policy_live);
			if (!ret && !a6_policy_live_charging()) {
				a6_policy_latch_fault_live();
				ret = -ESTALE;
			}
			if (ret)
				a6_auto_stop(ret, false);
		}
		a6_policy_record(a6_policy_active ? 'C' : 'H');
		return;
	}
	if (!a6_auto_attached) {
		if (a6_auto_held || a6_policy_keep_input)
			a6_auto_stop(-ENOLINK, false);
		a6_policy_record('D');
		return;
	}
	if (!a6_auto_held && !a6_auto_fault) {
		/* Attached: put the PMU under this driver's guards first. */
		if (a6_policy_disable(true))
			a6_auto_fault = true;
	}
	if (a6_auto_fault) {
		a6_policy_record('F');
		return;
	}
	if (a6_auto_paused) {
		a6_policy_record('P');
		return;
	}
	if (a6_auto_held && a6_policy_cell_ok() &&
	    (!a6_auto_thermal_hold ||
	     a6_policy_tbat_c <= A6_AUTO_TBAT_RESUME) &&
	    a6_policy_vbat_mv <= A6_AUTO_RESUME_MV &&
	    time_after_eq(jiffies, a6_auto_last_stop + A6_AUTO_REARM_GAP)) {
		ret = a6_policy_snapshot(a6_policy_initial);
		if (!ret && !a6_auto_state_known(a6_policy_initial))
			ret = -EPROTO;
		if (!ret)
			ret = a6_policy_program(false);
		if (ret) {
			a6_policy_result = ret;
			a6_auto_last_stop = jiffies;
			if (ret == -EPROTO || ret == -EUCLEAN)
				a6_auto_fault = true;
		} else {
			a6_auto_thermal_hold = false;
			a6_auto_arms++;
		}
	}
	a6_policy_record(a6_policy_active ? 'C' : 'H');
}

static void a6_policy_tick(struct work_struct *work)
{
	int ret;
	mutex_lock(&a6_touch_lock);
	if (a6_auto_enabled) {
		a6_auto_step();
	} else if (a6_policy_stopping) {
		a6_policy_disable(a6_policy_keep_input);
	} else if (a6_policy_active) {
		ret = a6_policy_leased &&
			time_after_eq(jiffies, a6_policy_deadline) ? -ETIME :
			a6_policy_check();
		if (!ret) {
			ret = a6_policy_snapshot(a6_policy_live);
			if (!ret && !a6_policy_live_charging()) {
				a6_policy_latch_fault_live();
				ret = -ESTALE;
			}
		}
		if (ret) {
			a6_policy_result = ret;
			a6_policy_disable(ret == -ETIME || ret == -ERANGE);
		}
	}
	if (a6_auto_enabled || a6_policy_active || a6_policy_stopping)
		schedule_delayed_work(&a6_policy_work, 2 * HZ);
	mutex_unlock(&a6_touch_lock);
}

static ssize_t a6_policy_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_D1972_500_CLASS_CANDIDATE_V5 active=%u stopping=%u ever_armed=%u clean_stop_seen=%u arm_count=%u keep_input=%u result=%d disable_result=%d seconds_left=%lu\n",
		a6_policy_active, a6_policy_stopping, a6_policy_ever_armed,
		a6_policy_clean_stop_seen,
		a6_policy_arm_count,
		a6_policy_keep_input,
		a6_policy_result, a6_policy_disable_result,
		a6_policy_active && a6_policy_leased &&
		time_before(jiffies, a6_policy_deadline) ?
		(a6_policy_deadline - jiffies) / HZ : 0UL);
	n += sysfs_emit_at(buf, n,
		"auto=%u paused=%u fault=%u attached=%u held=%u thermal_hold=%u auto_arms=%u tbat_max_c=%d tbat_resume_c=%d resume_mv=%d\n",
		a6_auto_enabled, a6_auto_paused, a6_auto_fault,
		a6_auto_attached, a6_auto_held, a6_auto_thermal_hold,
		a6_auto_arms, A6_POLICY_TBAT_MAX, A6_AUTO_TBAT_RESUME,
		A6_AUTO_RESUME_MV);
	n += sysfs_emit_at(buf, n,
		"vbus_mv=%u vbat_mv=%u tbat_c_candidate=%d initial_1b_3f_43_45_46=%*phN live_1b_3f_43_45_46=%*phN\n",
		a6_policy_vbus_mv, a6_policy_vbat_mv, a6_policy_tbat_c,
		5, a6_policy_initial, 5, a6_policy_live);
	n += sysfs_emit_at(buf, n,
		"fault_live_valid=%u fault_live_1b_3f_43_45_46=%*phN\n",
		a6_policy_fault_live_valid, 5, a6_policy_fault_live);
	mutex_unlock(&a6_touch_lock);
	return n;
}

/* Oldest first: jiffies, state (C charging, H held, P paused, D detached,
 * F fault, S stopping, E measurement error), VBUS, VBAT, TBAT.
 */
static ssize_t a6_policy_samples_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	unsigned int count, first, i;
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	count = min(a6_policy_sample_count, (unsigned int)A6_POLICY_SAMPLES);
	first = a6_policy_sample_count - count;
	n = sysfs_emit(buf, "A6_D1972_AUTO_SAMPLES_V1 hz=%d total=%u\n",
		       HZ, a6_policy_sample_count);
	for (i = 0; i < count; i++) {
		unsigned int k = (first + i) % A6_POLICY_SAMPLES;
		n += sysfs_emit_at(buf, n, "%lu %c %u %u %d\n",
			a6_policy_samples[k].when, a6_policy_samples[k].state,
			a6_policy_samples[k].vbus_mv,
			a6_policy_samples[k].vbat_mv,
			a6_policy_samples[k].tbat_c);
	}
	mutex_unlock(&a6_touch_lock);
	return n;
}

/* Stable inherited shutdown state only. Stock also reads 0x01..0x09, but
 * those changed after one observation and may be read-to-clear.
 * This path submits no PMU writes.
 */
static ssize_t a6_policy_shutdown_regs_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	static const u8 regs[] = {
		0x68, 0x69, 0x6a, 0x6b, 0x6c, 0x6d,
		0x6e, 0x6f, 0x70, 0x71, 0x72, 0x73,
		0xb0, 0xb9, 0x1b,
	};
	u8 values[ARRAY_SIZE(regs)];
	unsigned int i;
	ssize_t n = 0;
	int ret;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	ret = a6_power_validate();
	if (ret)
		goto out;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_policy_reg(regs[i], &values[i], false);
		if (ret)
			goto out;
	}
	n = sysfs_emit(buf, "A6_D1972_SHUTDOWN_REGS_V2\n");
	for (i = 0; i < ARRAY_SIZE(regs); i++)
		n += sysfs_emit_at(buf, n, "%02x=%02x%c", regs[i], values[i],
			(i + 1) % 8 == 0 || i + 1 == ARRAY_SIZE(regs) ? '\n' : ' ');
out:
	a6_power_recover();
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : n;
}

static ssize_t a6_policy_control_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	int ret = 0;
	bool arm = sysfs_streq(buf, "arm-500-class-10m-after-tbat-check");
	bool rearm = sysfs_streq(buf, "rearm-500-class-10m-after-tbat-check");
	bool autorun = sysfs_streq(buf, "auto");
	bool pause = sysfs_streq(buf, "pause");
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!arm && !rearm && !autorun && !pause && !sysfs_streq(buf, "disarm"))
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (autorun) {
		if (a6_policy_stopping) {
			ret = -EBUSY;
			goto out;
		}
		a6_auto_enabled = true;
		a6_auto_paused = false;
		a6_auto_fault = false;
		a6_auto_flip = 0;
		a6_auto_last_stop = jiffies - A6_AUTO_REARM_GAP;
		mod_delayed_work(system_percpu_wq, &a6_policy_work, 0);
		goto out;
	}
	if (pause) {
		if (!a6_auto_enabled) {
			ret = -EINVAL;
			goto out;
		}
		a6_auto_paused = true;
		if (a6_policy_active) {
			a6_policy_result = 0;
			ret = a6_policy_disable(true);
			a6_auto_last_stop = jiffies;
		}
		goto out;
	}
	if (!arm && !rearm) {
		a6_auto_enabled = false;
		a6_auto_paused = false;
		ret = a6_policy_active || a6_policy_stopping ?
			a6_policy_disable(a6_policy_vbus_ok()) : 0;
		if (a6_policy_stopping)
			schedule_delayed_work(&a6_policy_work, 2 * HZ);
		goto out;
	}
	if (a6_auto_enabled) {
		ret = -EBUSY;
		goto out;
	}
	if (a6_policy_active || a6_policy_stopping || a6_policy_arm_count >= 3 ||
	    (arm && a6_policy_ever_armed) || (rearm && !a6_policy_ever_armed)) {
		ret = -EALREADY;
		goto out;
	}
	/* The operator must first inspect the separate, restored TBAT probe
	 * against the immediately preceding iOS temperature snapshot.
	 */
	if (!a6_tbat_attempted || a6_tbat_result || !a6_tbat_restored) {
		ret = -EPERM;
		goto out;
	}
	ret = a6_policy_check();
	if (ret) goto out;
	ret = a6_policy_snapshot(a6_policy_initial);
	if (ret) goto out;
	if (arm) {
		/* First arm requires the observed N42 inheritance. */
		if (memcmp(a6_policy_initial,
			   (u8[]){0, 3, 0x3f, 0x1e, 0xa1}, 5)) {
			ret = -EPROTO;
			goto out;
		}
	} else {
		/* Renewal requires our own verified clean stop, still on USB. */
		if (!a6_policy_keep_input || a6_policy_disable_result ||
		    a6_policy_vbat_mv > 4200 ||
		    a6_policy_initial[0] != 4 || a6_policy_initial[1] ||
		    a6_policy_initial[2] != A6_POLICY_INPUT ||
		    (a6_policy_initial[3] & 0x3f) > A6_POLICY_INPUT ||
		    a6_policy_initial[4] != 0xa1) {
			ret = -EPROTO;
			goto out;
		}
	}
	ret = a6_policy_program(true);
	if (a6_policy_active || a6_policy_stopping)
		schedule_delayed_work(&a6_policy_work, 2 * HZ);
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_policy_status_attr =
	__ATTR(status, 0400, a6_policy_status_show, NULL);
static struct kobj_attribute a6_policy_samples_attr =
	__ATTR(samples, 0400, a6_policy_samples_show, NULL);
static struct kobj_attribute a6_policy_shutdown_regs_attr =
	__ATTR(shutdown_regs, 0400, a6_policy_shutdown_regs_show, NULL);
static struct kobj_attribute a6_policy_control_attr =
	__ATTR(control, 0200, NULL, a6_policy_control_store);
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
static ssize_t a6_stock_off_trial_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	return sysfs_emit(buf, "A6_STOCK_OFF_CANDIDATE_V1 armed=%u stage=%u result=%d\n",
		a6_stock_off_armed, a6_stock_off_stage, a6_stock_off_result);
}

static ssize_t a6_stock_off_trial_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	int ret = 0;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	if (sysfs_streq(buf, "disarm")) {
		a6_stock_off_armed = false;
	} else if (!sysfs_streq(buf, "arm-unplugged-once")) {
		ret = -EINVAL;
	} else if (a6_stock_off_armed || a6_auto_enabled ||
		   a6_policy_active || a6_policy_stopping) {
		ret = -EBUSY;
	} else {
		a6_stock_off_stage = 0;
		a6_stock_off_result = 0;
		a6_stock_off_armed = true;
	}
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_stock_off_trial_attr =
	__ATTR(stock_off_trial, 0600, a6_stock_off_trial_show,
	       a6_stock_off_trial_store);
#endif
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
static ssize_t a6_low_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_LOW_BATTERY_CANDIDATE_V3 enabled=%u attended_trial=%u attended_plugged=%u triggered=%u plugged=%u streak=%u required=%u samples=%u result=%d vbus_mv=%u vbat_mv=%u threshold_mv=%u plugged_critical_mv=%u\n",
		a6_low_enabled, a6_low_attended_trial, a6_low_attended_plugged,
		a6_low_triggered,
		a6_low_plugged,
		a6_low_streak, A6_LOW_STREAK_SAMPLES, a6_low_samples,
		a6_low_result, a6_low_vbus_mv, a6_low_vbat_mv,
		a6_low_attended_trial ? 4500 : A6_LOW_VBAT_MV,
		A6_LOW_PLUGGED_CRITICAL_MV);
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_low_control_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	bool enable = sysfs_streq(buf, "monitor");
	bool plugged_trial = sysfs_streq(buf, "attended-plugged-trial-once");
	bool trial = plugged_trial || sysfs_streq(buf, "attended-trial-once");
	int ret = 0;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!enable && !trial && !sysfs_streq(buf, "disarm"))
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (!enable && !trial) {
		a6_low_enabled = false;
		a6_low_attended_trial = false;
		a6_low_attended_plugged = false;
		a6_low_streak = 0;
	} else if (a6_low_triggered || a6_low_enabled ||
		   a6_stock_off_armed) {
		ret = -EBUSY;
	} else {
		a6_low_enabled = true;
		a6_low_attended_trial = trial;
		a6_low_attended_plugged = plugged_trial;
		a6_low_streak = 0;
		a6_low_plugged = false;
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
		a6_low_screen_failure = false;
#endif
		a6_low_samples = 0;
		a6_low_result = 0;
		mod_delayed_work(system_percpu_wq, &a6_low_work, 0);
	}
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_low_status_attr =
	__ATTR(low_battery_status, 0400, a6_low_status_show, NULL);
static struct kobj_attribute a6_low_control_attr =
	__ATTR(low_battery_control, 0200, NULL, a6_low_control_store);
#endif
static struct attribute *a6_policy_attrs[] = {
	&a6_policy_status_attr.attr, &a6_policy_samples_attr.attr,
	&a6_policy_shutdown_regs_attr.attr, &a6_policy_control_attr.attr,
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
	&a6_stock_off_trial_attr.attr,
#endif
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
	&a6_low_status_attr.attr, &a6_low_control_attr.attr,
#endif
	NULL
};
static const struct attribute_group a6_policy_group = {
	.name = "a6_charger_policy", .attrs = a6_policy_attrs
};
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
/* Attended, opt-in reproduction of the stock no-source branch. The measured
 * N42 inheritance is an exact preflight, not a claim that these bytes are
 * constants across phones or boots. Manual trials stop on a failed step;
 * a low-battery emergency makes one best-effort reset into iOS instead.
 */
static int a6_policy_stock_off(void)
{
	static const u8 inherited[] = {
		0xb9, 0xba, 0x09, 0x7a, 0x49, 0xda,
		0xbb, 0xea, 0x09, 0xaa, 0x09, 0xb9
	};
	static const u8 fixed[] = {
		0x88, 0xff, 0xff, 0xff, 0xff, 0xae, 0xff, 0xff, 0xff
	};
	u8 block[12], first[9], reg, b0, b9, off, charge_target, input_limit;
	unsigned int i;
	unsigned int min_vbat_mv = 3500;
	bool b0_zero_allowed = false;
	int ret;

#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
	if (a6_low_triggered)
		min_vbat_mv = 3200;
#endif
	a6_stock_off_stage = 1;
	ret = a6_policy_measure();
	if (ret)
		return ret;
	if (a6_policy_vbus_mv >= 500 ||
	    a6_policy_vbat_mv < min_vbat_mv)
		return -ERANGE;
	ret = a6_power_byte(0x1e, &reg, false);
	if (ret)
		return ret;
	if (reg)
		return -EPROTO;
	ret = a6_policy_reg(0xb0, &b0, false);
	if (ret)
		return ret;
	ret = a6_policy_reg(0xb9, &b9, false);
	if (ret)
		return ret;
	ret = a6_policy_reg(0x1b, &off, false);
	if (ret)
		return ret;
	ret = a6_policy_reg(0x3f, &charge_target, false);
	if (ret)
		return ret;
	ret = a6_policy_reg(0x43, &input_limit, false);
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(block); i++) {
		ret = a6_policy_reg(0x68 + i, &block[i], false);
		if (ret)
			return ret;
	}
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
	/* This phone reported b0=00 while detached with VBUS at 4 mV.
	 * Stock's b0 & 0x2f yields zero for both 00 and the earlier 40.
	 */
	b0_zero_allowed = a6_low_triggered && b0 == 0;
#endif
	if ((b0 != 0x40 && !b0_zero_allowed) || b9 ||
	    !(off == 0 || (off == 4 && a6_policy_clean_stop_seen &&
			   !a6_policy_active && !a6_policy_stopping &&
			   !a6_policy_disable_result && !charge_target &&
			   !(input_limit & 0x3f))) ||
	    memcmp(block, inherited, sizeof(inherited)))
		return -EPROTO;

	a6_stock_off_stage = 2;
	reg = 0;
	ret = a6_policy_reg(0x7d, &reg, true);
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(first); i++) {
		ret = a6_policy_reg(0x01 + i, &first[i], false);
		if (ret)
			return ret;
	}
	a6_stock_off_stage = 3;
	ret = a6_power_stock_off_block(0x12, fixed, ARRAY_SIZE(fixed));
	if (ret)
		return ret;
	reg = 1; /* stock +0x5c20 with a zero UPO counter */
	ret = a6_policy_reg(0x62, &reg, true);
	if (ret)
		return ret;
	reg = 0;
	ret = a6_policy_reg(0xa2, &reg, true);
	if (ret)
		return ret;
	ret = a6_policy_reg(0xa4, &reg, true);
	if (ret)
		return ret;
	/* Detached/no-source branch r5=1, +0xbf=0: (0x40 & 0x2f). */
	reg = b0 & 0x2f;
	ret = a6_policy_reg(0xb0, &reg, true);
	if (ret)
		return ret;
	a6_stock_off_stage = 4;
	ret = a6_policy_reg(0xb9, &b9, false);
	if (ret)
		return ret;
	if (b9)
		return -EPROTO;
	for (i = 0; i < ARRAY_SIZE(block); i++) {
		ret = a6_policy_reg(0x68 + i, &block[i], false);
		if (ret)
			return ret;
		if (block[i] >= 0x60)
			block[i] &= ~2;
	}
	a6_stock_off_stage = 5;
	ret = a6_power_stock_off_block(0x68, block, ARRAY_SIZE(block));
	if (ret)
		return ret;
	for (i = 0; i < ARRAY_SIZE(first); i++) {
		ret = a6_policy_reg(0x01 + i, &first[i], false);
		if (ret)
			return ret;
	}
	a6_stock_off_stage = 6;
	off |= 1;
	return a6_policy_reg(0x1b, &off, true);
}
#endif
/* Experimental power-off: stock _shutdownGated ends, on both its block-write
 * paths, by setting D1972 0x1b bit 0 and looping. This tries that final
 * write alone, without the preceding 0x12 and 0x68..0x73 block writes.
 * Runs in the sleepable prepare stage, after device shutdown. The charge
 * request is cleared first so charging never outlives these guards.
 */
static int a6_policy_power_off(struct sys_off_data *data)
{
	u8 v;
	int ret;

	cancel_delayed_work_sync(&a6_policy_work);
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
	cancel_delayed_work_sync(&a6_low_work);
#endif
	mutex_lock(&a6_touch_lock);
	a6_auto_enabled = false;
	if (a6_policy_active || a6_policy_stopping || a6_auto_held)
		a6_policy_disable(false);
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
	if (a6_stock_off_armed) {
		a6_stock_off_armed = false;
		a6_power_recover();
		ret = a6_policy_stock_off();
		a6_stock_off_result = ret;
		pr_emerg("a6-d1972: stock-off stage=%u result=%d\n",
			a6_stock_off_stage, ret);
		if (!ret) {
			msleep(2000);
			mutex_unlock(&a6_touch_lock);
			return NOTIFY_DONE;
		}
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
		/* The emergency path must not halt and drain after a refused stock
		 * sequence. Best-effort legacy reset hands charging back to iOS.
		 */
		if (!a6_low_triggered) {
			mutex_unlock(&a6_touch_lock);
			return NOTIFY_DONE;
		}
		pr_emerg("a6-d1972: low-battery stock-off failed; trying iOS reset\n");
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
		if (a6_low_attended_trial && a6_low_screen_ok) {
			a6_low_screen_failure = true;
			a6_low_screen_stage = a6_stock_off_stage;
			a6_low_screen_stock_result = ret;
			a6_low_screen_draw();
			msleep(20000);
		}
#endif
#else
		mutex_unlock(&a6_touch_lock);
		return NOTIFY_DONE;
#endif
	}
#endif
	ret = a6_power_validate();
	a6_power_recover();
	if (!ret)
		ret = a6_policy_reg(0x1b, &v, false);
	if (!ret) {
		v |= 1;
		ret = a6_policy_reg(0x1b, &v, true);
	}
	pr_emerg("a6-d1972: power-off request 0x1b|=1 result=%d\n", ret);
	if (!ret)
		msleep(2000);
	pr_emerg("a6-d1972: still running after power-off request\n");
	mutex_unlock(&a6_touch_lock);
	return NOTIFY_DONE;
}

/* The work is done in the prepare stage above. Without a handler in the
 * final POWER_OFF chain, the reboot syscall turns power-off into halt and
 * never runs the prepare stage.
 */
static int a6_policy_power_off_final(struct sys_off_data *data)
{
	return NOTIFY_DONE;
}

static int __init a6_policy_init(void)
{
	struct sys_off_handler *handler;
	int ret;

	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c)
		return -ENODEV;
	INIT_DELAYED_WORK(&a6_policy_work, a6_policy_tick);
#ifdef A6_D1972_LOW_BATTERY_CANDIDATE
	INIT_DELAYED_WORK(&a6_low_work, a6_low_tick);
#ifdef A6_LOW_BATTERY_TRACE_SCREEN
	a6_low_screen_ok = READ_ONCE(a6_fb_base_saved) == 0xbf7aa000 &&
		READ_ONCE(a6_fb_stride_saved) == 640 * 4 &&
		a6_fb_mapping_valid(0xbf7aa000, 640 * 1136 * 4);
	pr_info("A6_LOW_BATTERY_TRACE_SCREEN_V1 ready=%u\n",
		a6_low_screen_ok);
#endif
#endif
	ret = sysfs_create_group(firmware_kobj, &a6_policy_group);
	if (ret)
		return ret;
	handler = register_sys_off_handler(SYS_OFF_MODE_POWER_OFF_PREPARE,
			SYS_OFF_PRIO_DEFAULT, a6_policy_power_off, NULL);
	if (IS_ERR(handler))
		return PTR_ERR(handler);
	ret = PTR_ERR_OR_ZERO(register_sys_off_handler(SYS_OFF_MODE_POWER_OFF,
			SYS_OFF_PRIO_LOW, a6_policy_power_off_final, NULL));
	if (ret)
		return ret;
#ifdef A6_D1972_BOOT_DEFAULTS
	/* Stage A candidate: the proven bounded policy and independent voltage
	 * monitor start without a USB shell. Both retain their sysfs controls.
	 */
	a6_auto_enabled = true;
	a6_auto_last_stop = jiffies - A6_AUTO_REARM_GAP;
	a6_low_enabled = true;
	mod_delayed_work(system_percpu_wq, &a6_low_work, 0);
	mod_delayed_work(system_percpu_wq, &a6_policy_work, 0);
	pr_info("A6_BOOT_DEFAULTS_V1 auto=1 monitor=1 threshold_mv=%u\n",
		A6_LOW_VBAT_MV);
#endif
	return 0;
}
late_initcall(a6_policy_init);

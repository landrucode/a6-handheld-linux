// SPDX-License-Identifier: GPL-2.0-only
/* Read-only N42 D1972 ADC channel 2 (TBAT) probe. The stock
 * AppleD1972PMU channel-name switch maps channel 2 to tbat, and
 * the N41/N42 schematic connects BATTERY_NTC to the PMU TBAT pin.
 * This returns raw ADC counts, not calibrated degrees.
 * The ADC selector is restored after each sample.
 * Caller-facing operations are root-only and one-shot per RAM boot.
 */
static bool a6_tbat_attempted, a6_tbat_restored;
static int a6_tbat_result, a6_tbat_cleanup_result;
static u8 a6_tbat_before[3], a6_tbat_after[3], a6_tbat_control;
static unsigned int a6_tbat_raw;

/* AppleD1972PMU: channel 2 at +0x3ac returns raw*40 in Q16; its
 * temperature path scales by 20000 and interpolates the 10k NTC LUT.
 * Keep this a candidate until checked against the stock iOS gauge.
 */
static const struct { unsigned int ohm; int c; } a6_tbat_ntc[] = {
	{ 188500, -40 }, { 144290, -35 }, { 111330, -30 },
	{ 86560, -25 }, { 67790, -20 }, { 53460, -15 },
	{ 42450, -10 }, { 33930, -5 }, { 27280, 0 },
	{ 22070, 5 }, { 17960, 10 }, { 14700, 15 },
	{ 12090, 20 }, { 10000, 25 }, { 8310, 30 },
	{ 6940, 35 }, { 5830, 40 }, { 4910, 45 },
	{ 4160, 50 }, { 3540, 55 }, { 3020, 60 },
	{ 2590, 65 }, { 2230, 70 }, { 1920, 75 },
	{ 1670, 80 }, { 1450, 85 }, { 1270, 90 },
	{ 1110, 95 }, { 980, 100 },
};

static int a6_tbat_candidate_c(unsigned int ohm)
{
	unsigned int i;

	if (ohm > a6_tbat_ntc[0].ohm ||
	    ohm < a6_tbat_ntc[ARRAY_SIZE(a6_tbat_ntc) - 1].ohm)
		return INT_MIN;
	for (i = 1; i < ARRAY_SIZE(a6_tbat_ntc); i++) {
		if (ohm >= a6_tbat_ntc[i].ohm) {
			unsigned int span = a6_tbat_ntc[i - 1].ohm - a6_tbat_ntc[i].ohm;
			unsigned int delta = a6_tbat_ntc[i - 1].ohm - ohm;
			return a6_tbat_ntc[i - 1].c + (int)(delta * 5 / span);
		}
	}
	return INT_MIN;
}

static ssize_t a6_tbat_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_D1972_TBAT_RAW_V1 attempted=%u result=%d cleanup_result=%d restored=%u\n",
		a6_tbat_attempted, a6_tbat_result,
		a6_tbat_cleanup_result, a6_tbat_restored);
	n += sysfs_emit_at(buf, n,
		"before_48_49_4a=%*phN control_48=%02x after_48_49_4a=%*phN raw=%u resistance_ohm_candidate=%u temp_c_candidate=%d\n",
		3, a6_tbat_before, a6_tbat_control,
		3, a6_tbat_after, a6_tbat_raw,
		(u32)((u64)a6_tbat_raw * 800000 / 65536),
		a6_tbat_candidate_c((u32)((u64)a6_tbat_raw * 800000 / 65536)));
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_tbat_sample_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	static const u8 regs[] = { 0x48, 0x49, 0x4a };
	u8 lo = 0, hi = 0, restore, verify = 0;
	unsigned int i;
	int ret, cr;
	bool maybe_written = false;

	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!sysfs_streq(buf, "sample-tbat-once-and-restore")) return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_tbat_attempted) { ret = -EALREADY; goto out; }
	ret = a6_power_validate();
	if (ret) goto out;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_vbus_xfer(regs[i], &a6_tbat_before[i], false);
		if (ret) goto out;
	}
	if (a6_tbat_before[0] & 0x60) { ret = -EBUSY; goto out; }
	a6_tbat_control = (a6_tbat_before[0] & 0x80) | 0x20 | 2;
	a6_tbat_attempted = true;
	maybe_written = true;
	ret = a6_vbus_xfer(0x48, &a6_tbat_control, true);
	if (ret) goto cleanup;
	msleep(10);
	ret = a6_vbus_xfer(0x49, &lo, false);
	if (ret) goto cleanup;
	ret = a6_vbus_xfer(0x4a, &hi, false);
	if (!ret) a6_tbat_raw = (lo & 0x0f) | (hi << 4);
cleanup:
	if (maybe_written) {
		a6_power_recover();
		restore = a6_tbat_before[0];
		cr = a6_vbus_xfer(0x48, &restore, true);
		if (cr) a6_tbat_cleanup_result = cr;
		a6_power_recover();
		cr = a6_vbus_xfer(0x48, &verify, false);
		if (cr && !a6_tbat_cleanup_result) a6_tbat_cleanup_result = cr;
		a6_tbat_restored = !a6_tbat_cleanup_result &&
			verify == a6_tbat_before[0] && a6_power_recover();
		if (!ret && !a6_tbat_restored) ret = -EUCLEAN;
	}
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		cr = a6_vbus_xfer(regs[i], &a6_tbat_after[i], false);
		if (cr && !a6_tbat_cleanup_result) a6_tbat_cleanup_result = cr;
	}
	if (!ret && a6_tbat_cleanup_result) ret = -EUCLEAN;
out:
	a6_tbat_result = ret;
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_tbat_status_attr = __ATTR(status, 0400, a6_tbat_status_show, NULL);
static struct kobj_attribute a6_tbat_sample_attr = __ATTR(sample, 0200, NULL, a6_tbat_sample_store);
static struct attribute *a6_tbat_attrs[] = {
	&a6_tbat_status_attr.attr, &a6_tbat_sample_attr.attr, NULL
};
static const struct attribute_group a6_tbat_group = {
	.name = "a6_tbat_adc", .attrs = a6_tbat_attrs
};
static int __init a6_tbat_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c)
		return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_tbat_group);
}
late_initcall(a6_tbat_init);

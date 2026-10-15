// SPDX-License-Identifier: GPL-2.0-only
/* One-shot D1972 VBUS ADC trial, root-triggered only. No charger-limit writes.
 * Stock AppleD1972PMU selects channel 15 in register 48, reads 49/4a, and
 * scales its raw result by 88 in Q16 volts. The scale is reported for
 * investigation until an external voltage cross-check is available.
 */
static bool a6_vbus_attempted, a6_vbus_restored;
static int a6_vbus_result, a6_vbus_cleanup_result;
static u8 a6_vbus_before[3], a6_vbus_after[3], a6_vbus_control;
static unsigned int a6_vbus_raw;

static int a6_vbus_xfer(u8 reg, u8 *value, bool write)
{
	return a6_power_xfer(reg, value, write, false);
}

static ssize_t a6_vbus_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, "A6_D1972_VBUS_ADC_V1\nattempted=%u result=%d cleanup_result=%d restored=%u\n",
		a6_vbus_attempted, a6_vbus_result, a6_vbus_cleanup_result,
		a6_vbus_restored);
	n += sysfs_emit_at(buf, n,
		"before_48_49_4a=%*phN control_48=%02x after_48_49_4a=%*phN raw=%u vbus_candidate_mv=%u\n",
		3, a6_vbus_before, a6_vbus_control, 3, a6_vbus_after,
		a6_vbus_raw, a6_vbus_raw * 88 * 1000 / 65536);
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_vbus_sample_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	static const u8 regs[] = { 0x48, 0x49, 0x4a };
	u8 lo = 0, hi = 0, restore, verify = 0;
	unsigned int i;
	int ret, cr;
	bool maybe_written = false;

	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!sysfs_streq(buf, "sample-vbus-once-and-restore")) return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_vbus_attempted) { ret = -EALREADY; goto out; }
	ret = a6_power_validate();
	if (ret) goto out;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_vbus_xfer(regs[i], &a6_vbus_before[i], false);
		if (ret) goto out;
	}
	/* Refuse another active conversion; preserve the unrelated upper bit. */
	if (a6_vbus_before[0] & 0x60) { ret = -EBUSY; goto out; }
	a6_vbus_control = (a6_vbus_before[0] & 0x80) | 0x20 | 15;
	a6_vbus_attempted = true;
	maybe_written = true; /* Even a failed I2C submission may have changed 48. */
	ret = a6_vbus_xfer(0x48, &a6_vbus_control, true);
	if (ret) goto cleanup;
	msleep(10);
	ret = a6_vbus_xfer(0x49, &lo, false);
	if (ret) goto cleanup;
	ret = a6_vbus_xfer(0x4a, &hi, false);
	if (!ret) a6_vbus_raw = (lo & 0x0f) | (hi << 4);
cleanup:
	if (maybe_written) {
		a6_power_recover();
		restore = a6_vbus_before[0];
		cr = a6_vbus_xfer(0x48, &restore, true);
		if (cr) a6_vbus_cleanup_result = cr;
		a6_power_recover();
		cr = a6_vbus_xfer(0x48, &verify, false);
		if (cr && !a6_vbus_cleanup_result) a6_vbus_cleanup_result = cr;
		a6_vbus_restored = !a6_vbus_cleanup_result &&
			verify == a6_vbus_before[0] && a6_power_recover();
		if (!ret && !a6_vbus_restored) ret = -EUCLEAN;
	}
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		cr = a6_vbus_xfer(regs[i], &a6_vbus_after[i], false);
		if (cr && !a6_vbus_cleanup_result) a6_vbus_cleanup_result = cr;
	}
	if (!ret && a6_vbus_cleanup_result) ret = -EUCLEAN;
out:
	a6_vbus_result = ret;
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_vbus_status_attr = __ATTR(status, 0400, a6_vbus_status_show, NULL);
static struct kobj_attribute a6_vbus_sample_attr = __ATTR(sample, 0200, NULL, a6_vbus_sample_store);
static struct attribute *a6_vbus_attrs[] = {
	&a6_vbus_status_attr.attr, &a6_vbus_sample_attr.attr, NULL
};
static const struct attribute_group a6_vbus_group = {
	.name = "a6_vbus_adc", .attrs = a6_vbus_attrs
};
static int __init a6_vbus_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c)
		return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_vbus_group);
}
late_initcall(a6_vbus_init);

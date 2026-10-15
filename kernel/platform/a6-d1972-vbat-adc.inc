// SPDX-License-Identifier: GPL-2.0-only
/* One-shot D1972 VBAT ADC trial. Stock selector 4, Q16-volts scaling. */
static bool a6_vbat_attempted, a6_vbat_restored;
static int a6_vbat_result, a6_vbat_cleanup_result;
static u8 a6_vbat_before[3], a6_vbat_after[3], a6_vbat_control;
static unsigned int a6_vbat_raw;
#ifdef A6_D1972_VBAT_MONITOR
static unsigned int a6_vbat_samples;
static unsigned long a6_vbat_next_jiffies;
#endif

static ssize_t a6_vbat_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, "A6_D1972_VBAT_ADC_V1\nattempted=%u result=%d cleanup_result=%d restored=%u\n",
		a6_vbat_attempted, a6_vbat_result, a6_vbat_cleanup_result,
		a6_vbat_restored);
	n += sysfs_emit_at(buf, n,
		"before_48_49_4a=%*phN control_48=%02x after_48_49_4a=%*phN raw=%u vbat_candidate_mv=%u\n",
		3, a6_vbat_before, a6_vbat_control, 3, a6_vbat_after,
		a6_vbat_raw, 2500 + a6_vbat_raw * 32000 / 65536);
#ifdef A6_D1972_VBAT_MONITOR
	n += sysfs_emit_at(buf, n, "samples=%u next_jiffies=%lu now_jiffies=%lu\n",
		a6_vbat_samples, a6_vbat_next_jiffies, jiffies);
#endif
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_vbat_sample_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	static const u8 regs[] = { 0x48, 0x49, 0x4a };
	u8 lo = 0, hi = 0, restore, verify = 0;
	unsigned int i;
	int ret, cr;
	bool maybe_written = false;

	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
#ifdef A6_D1972_VBAT_MONITOR
	if (!sysfs_streq(buf, "sample-vbat-and-restore")) return -EINVAL;
#else
	if (!sysfs_streq(buf, "sample-vbat-once-and-restore")) return -EINVAL;
#endif
	mutex_lock(&a6_touch_lock);
	if (a6_vbat_attempted) {
#ifdef A6_D1972_VBAT_MONITOR
		if (a6_vbat_result || !a6_vbat_restored) { ret = -EIO; goto out; }
		if (time_before(jiffies, a6_vbat_next_jiffies)) {
			ret = -EAGAIN; goto out;
		}
#else
		ret = -EALREADY; goto out;
#endif
	}
	ret = a6_power_validate();
	if (ret) goto out;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_vbus_xfer(regs[i], &a6_vbat_before[i], false);
		if (ret) goto out;
	}
	if (a6_vbat_before[0] & 0x60) { ret = -EBUSY; goto out; }
	a6_vbat_control = (a6_vbat_before[0] & 0x80) | 0x20 | 4;
	a6_vbat_attempted = true;
	maybe_written = true;
	ret = a6_vbus_xfer(0x48, &a6_vbat_control, true);
	if (ret) goto cleanup;
	msleep(10);
	ret = a6_vbus_xfer(0x49, &lo, false);
	if (ret) goto cleanup;
	ret = a6_vbus_xfer(0x4a, &hi, false);
	if (!ret) a6_vbat_raw = (lo & 0x0f) | (hi << 4);
cleanup:
	if (maybe_written) {
		a6_power_recover();
		restore = a6_vbat_before[0];
		cr = a6_vbus_xfer(0x48, &restore, true);
		if (cr) a6_vbat_cleanup_result = cr;
		a6_power_recover();
		cr = a6_vbus_xfer(0x48, &verify, false);
		if (cr && !a6_vbat_cleanup_result) a6_vbat_cleanup_result = cr;
		a6_vbat_restored = !a6_vbat_cleanup_result &&
			verify == a6_vbat_before[0] && a6_power_recover();
		if (!ret && !a6_vbat_restored) ret = -EUCLEAN;
	}
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		cr = a6_vbus_xfer(regs[i], &a6_vbat_after[i], false);
		if (cr && !a6_vbat_cleanup_result) a6_vbat_cleanup_result = cr;
	}
	if (!ret && a6_vbat_cleanup_result) ret = -EUCLEAN;
#ifdef A6_D1972_VBAT_MONITOR
	if (!ret) {
		a6_vbat_samples++;
		a6_vbat_next_jiffies = jiffies + 60 * HZ;
	}
#endif
out:
	if (a6_vbat_attempted && ret != -EAGAIN)
		a6_vbat_result = ret;
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_vbat_status_attr = __ATTR(status, 0400, a6_vbat_status_show, NULL);
static struct kobj_attribute a6_vbat_sample_attr = __ATTR(sample, 0200, NULL, a6_vbat_sample_store);
static struct attribute *a6_vbat_attrs[] = {
	&a6_vbat_status_attr.attr, &a6_vbat_sample_attr.attr, NULL
};
static const struct attribute_group a6_vbat_group = {
	.name = "a6_vbat_adc", .attrs = a6_vbat_attrs
};
static int __init a6_vbat_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c)
		return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_vbat_group);
}
late_initcall(a6_vbat_init);

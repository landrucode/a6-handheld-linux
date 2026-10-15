// SPDX-License-Identifier: GPL-2.0-only
/* Explicit N42 one-shot: ordinary AUDIO/MCA0 gates only. No ACS, amp or PCM writes. */
static void __iomem *a6_audio_mca;
static bool a6_audio_attempted;
static int a6_audio_result, a6_audio_cleanup;
static u32 a6_audio_before[2], a6_audio_on[2], a6_audio_after[2];
static u32 a6_audio_id[2], a6_audio_capacity[2];
static bool a6_audio_sampled;
static const u32 a6_audio_gate_offsets[] = { 0xa0, 0xe0 };

static int a6_audio_wait_gate(unsigned int i, u32 expected)
{
	u32 value;
	return readl_poll_timeout(a6_touch_pmgr + a6_audio_gate_offsets[i], value,
		value != U32_MAX && (value & 0xff) == expected, 10, 100000);
}

static ssize_t a6_audio_run_store(struct kobject *kobj,
	struct kobj_attribute *attr, const char *buf, size_t count)
{
	bool changed[2] = { false, false };
	unsigned int i, tries;
	u32 value;
	int ret = 0, cleanup = 0;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "snapshot-enable-restore"))
		return -EINVAL;
	/* Charger uses this same mutex. Bounded acquisition; no independent I2C owner. */
	for (tries = 0; tries < 100; tries++) {
		if (mutex_trylock(&a6_touch_lock))
			break;
		usleep_range(1000, 2000);
	}
	if (tries == 100)
		return -EBUSY;
	if (a6_audio_attempted) {
		ret = -EALREADY;
		goto unlock;
	}
	a6_audio_attempted = true;
	/* Parent first. All passive validation precedes the first write. */
	for (i = 0; i < 2; i++) {
		value = readl(a6_touch_pmgr + a6_audio_gate_offsets[i]);
		a6_audio_before[i] = value;
		if (value == U32_MAX || value != readl(a6_touch_pmgr + a6_audio_gate_offsets[i]) ||
		    ((value & 0xff) != 0 && (value & 0xff) != 0xff)) {
			ret = -EBUSY;
			goto restore;
		}
	}
	for (i = 0; i < 2; i++) {
		if ((a6_audio_before[i] & 0xff) == 0) {
			changed[i] = true; /* Cleanup includes a partially acknowledged request. */
			writel(a6_audio_before[i] | 0xf, a6_touch_pmgr + a6_audio_gate_offsets[i]);
			ret = a6_audio_wait_gate(i, 0xff);
			if (ret)
				goto restore;
		}
		a6_audio_on[i] = readl(a6_touch_pmgr + a6_audio_gate_offsets[i]);
		if (a6_audio_on[i] == U32_MAX || (a6_audio_on[i] & 0xff) != 0xff) {
			ret = -EIO;
			goto restore;
		}
	}
	/* Identification and capacity only. Two samples distinguish unstable/stale evidence.
	 * This tests host accessibility with ordinary gates ON; no AE2/ACS prerequisites
	 * are asserted from the result. A bus transaction itself cannot be software-timed. */
	for (i = 0; i < 2; i++) {
		a6_audio_id[i] = readl(a6_audio_mca);
		a6_audio_capacity[i] = readl(a6_audio_mca + 4);
	}
	a6_audio_sampled = true;
restore:
	for (i = 2; i-- > 0;) {
		if (changed[i]) {
			writel(a6_audio_before[i], a6_touch_pmgr + a6_audio_gate_offsets[i]);
			if (a6_audio_wait_gate(i, a6_audio_before[i] & 0xff))
				cleanup = -EUCLEAN;
		}
		a6_audio_after[i] = readl(a6_touch_pmgr + a6_audio_gate_offsets[i]);
		if (changed[i] && a6_audio_after[i] != a6_audio_before[i])
			cleanup = -EUCLEAN;
	}
	a6_audio_result = ret;
	a6_audio_cleanup = cleanup;
	if (cleanup)
		ret = cleanup;
unlock:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static ssize_t a6_audio_status_show(struct kobject *kobj,
	struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, "A6_AUDIO_GATE_OBSERVE_V1\nattempted=%u result=%d cleanup=%d sampled=%u\n",
		a6_audio_attempted, a6_audio_result, a6_audio_cleanup, a6_audio_sampled);
	n += sysfs_emit_at(buf, n, "audio_gate=%08x/%08x/%08x mca_gate=%08x/%08x/%08x\n",
		a6_audio_before[0], a6_audio_on[0], a6_audio_after[0],
		a6_audio_before[1], a6_audio_on[1], a6_audio_after[1]);
	n += sysfs_emit_at(buf, n, "mca_id=%08x/%08x capacity=%08x/%08x\n",
		a6_audio_id[0], a6_audio_id[1], a6_audio_capacity[0], a6_audio_capacity[1]);
	mutex_unlock(&a6_touch_lock);
	return n;
}
static struct kobj_attribute a6_audio_run_attr = __ATTR(run, 0200, NULL, a6_audio_run_store);
static struct kobj_attribute a6_audio_status_attr = __ATTR(status, 0400, a6_audio_status_show, NULL);
static struct attribute *a6_audio_attrs[] = { &a6_audio_run_attr.attr, &a6_audio_status_attr.attr, NULL };
static const struct attribute_group a6_audio_group = { .name = "a6_audio", .attrs = a6_audio_attrs };
static int __init a6_audio_init(void)
{
	int ret;
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_pmgr || !a6_touch_gpio || !a6_touch_i2c)
		return -ENODEV;
	a6_audio_mca = ioremap(0x34196000, 0x1000);
	if (!a6_audio_mca)
		return -ENOMEM;
	ret = sysfs_create_group(firmware_kobj, &a6_audio_group);
	if (ret) {
		iounmap(a6_audio_mca);
		a6_audio_mca = NULL;
	}
	return ret;
}
late_initcall(a6_audio_init);

// SPDX-License-Identifier: GPL-2.0-only
/* Bounded n42/D1972 charger proof, NOT a persistent charger policy.
 * Caller-facing operations are root-only.
 * AppleD1972PMU evidence pins 43=input limit (30mA/code), 45=reported
 * current (30mA/code), 3f=charge target and 1b bit2=low-current mode.
 * The proof snapshots every writable byte, applies a bounded request for
 * ten seconds, samples register 45 (a setting, not measured cell current),
 * then restores in reverse. This historical diagnostic writes 0x3f before
 * 0x1b; the stock D1972 +0x68 method updates 0x1b before writing 0x3f.
 * Do not reuse this write sequence for the persistent Linux policy.
 */
#ifdef A6_CHARGER_ACTIVE_TRIAL
#define A6_CHARGER_INPUT_CODE 16 /* 480mA; below 500mA gadget descriptor */
#define A6_CHARGER_TARGET_CODE 13 /* 200mA = 70 + 13*10 */
#define A6_CHARGER_TARGET_MA 200
#define A6_CHARGER_COMMAND "prove-480in-200charge-10s-and-restore"
#define A6_CHARGER_MARKER "A6_CHARGER_ACTIVE_TRIAL_V1"
#else
#define A6_CHARGER_INPUT_CODE 3
#define A6_CHARGER_TARGET_CODE 3
#define A6_CHARGER_TARGET_MA 100
#define A6_CHARGER_COMMAND "prove-90ma-10s-and-restore"
#define A6_CHARGER_MARKER "A6_CHARGER_PROOF_V1"
#endif
#define A6_CHARGER_SAMPLES 11
#define A6_CHARGER_REQUIRED_OPS (5 + 3 + 4 + A6_CHARGER_SAMPLES + 3 + 5)
static bool a6_charger_observed, a6_charger_attempted, a6_charger_restored;
static int a6_charger_result, a6_charger_cleanup_result;
static u8 a6_charger_before[5], a6_charger_active[4], a6_charger_after[5];
static u8 a6_charger_current[A6_CHARGER_SAMPLES];

static int a6_charger_read(u8 reg, u8 *value)
{
	return a6_power_byte(reg, value, false);
}

static int a6_charger_write(u8 reg, u8 value)
{
	/* No arbitrary PMU writes can reach this transport. */
	if (!((reg == 0x43 && value == A6_CHARGER_INPUT_CODE) ||
	      (reg == 0x3f && value == A6_CHARGER_TARGET_CODE) ||
	      (reg == 0x1b && value == (a6_charger_before[0] & ~4))))
		return -EINVAL;
	return a6_power_set(reg, value);
}

static int a6_charger_snapshot(u8 *dst)
{
	static const u8 regs[] = { 0x1b, 0x3f, 0x43, 0x45, 0x46 };
	unsigned int i;
	int ret;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_charger_read(regs[i], &dst[i]);
		if (ret) return ret;
	}
	return 0;
}

static ssize_t a6_charger_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	unsigned int i;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, A6_CHARGER_MARKER "\nobserved=%u attempted=%u result=%d cleanup_result=%d restored=%u\n",
		a6_charger_observed, a6_charger_attempted, a6_charger_result,
		a6_charger_cleanup_result, a6_charger_restored);
	n += sysfs_emit_at(buf, n, "before_1b_3f_43_45_46=%*phN active_1b_3f_43_45=%*phN after_1b_3f_43_45_46=%*phN\n",
		5, a6_charger_before, 4, a6_charger_active, 5, a6_charger_after);
	n += sysfs_emit_at(buf, n, "before_input_limit_ma=%u before_reported_limit_ma=%u active_input_limit_ma=%u active_target_ma=%u reported_limit_samples_ma=",
		(a6_charger_before[2] & 0x3f) * 30, (a6_charger_before[3] & 0x3f) * 30,
		(a6_charger_active[2] & 0x3f) * 30, A6_CHARGER_TARGET_MA);
	for (i = 0; i < A6_CHARGER_SAMPLES; i++)
		n += sysfs_emit_at(buf, n, "%s%u", i ? "," : "", (a6_charger_current[i] & 0x3f) * 30);
	n += sysfs_emit_at(buf, n, "\n");
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_charger_observe_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	int ret;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!sysfs_streq(buf, "observe-charger")) return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_charger_observed || a6_charger_attempted) { ret = -EALREADY; goto out; }
	ret = a6_power_validate();
	if (!ret) ret = a6_charger_snapshot(a6_charger_before);
	if (!ret) a6_charger_observed = true;
	a6_charger_result = ret;
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static ssize_t a6_charger_prove_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	unsigned int i;
	int ret = 0, cr;
	bool wrote_43 = false, wrote_3f = false, wrote_1b = false;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!sysfs_streq(buf, A6_CHARGER_COMMAND)) return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (!a6_charger_observed || a6_charger_attempted) { ret = -EPERM; goto out; }
	a6_charger_attempted = true;
	ret = a6_power_validate();
	if (ret) goto cleanup;
	/* Reserve the entire remaining log before any PMU write is possible. */
	if (a6_power_transactions > A6_POWER_MAX - A6_CHARGER_REQUIRED_OPS) {
		ret = -ENOSPC;
		goto cleanup;
	}
	/* Refuse unexpected bank/common-register mutation between observation and proof. */
	ret = a6_charger_snapshot(a6_charger_after);
	if (ret || memcmp(a6_charger_before, a6_charger_after, 5)) {
		if (!ret) ret = -ESTALE;
		goto cleanup;
	}
#ifdef A6_CHARGER_ACTIVE_TRIAL
	/* This candidate is specific to the measured N42 boot state. */
	if (a6_charger_before[0] != 0 || a6_charger_before[1] != 3 ||
	    a6_charger_before[2] != 0x3f || a6_charger_before[3] != 0x1e ||
	    a6_charger_before[4] != 0xa1) {
		ret = -EPROTO;
		goto cleanup;
	}
#endif
	/* Program the limits before selecting the matching normal-current mode. */
	wrote_43 = true;
	ret = a6_charger_write(0x43, A6_CHARGER_INPUT_CODE);
	if (ret) goto cleanup;
	wrote_3f = true;
	ret = a6_charger_write(0x3f, A6_CHARGER_TARGET_CODE);
	if (ret) goto cleanup;
	wrote_1b = true;
	ret = a6_charger_write(0x1b, a6_charger_before[0] & ~4);
	if (ret) goto cleanup;
	for (i = 0; i < 4; i++) {
		static const u8 regs[] = { 0x1b, 0x3f, 0x43, 0x45 };
		ret = a6_charger_read(regs[i], &a6_charger_active[i]);
		if (ret) goto cleanup;
	}
	if ((a6_charger_active[0] & 4) ||
	    a6_charger_active[1] != A6_CHARGER_TARGET_CODE ||
	    a6_charger_active[2] != A6_CHARGER_INPUT_CODE) {
		ret = -EIO;
		goto cleanup;
	}
	for (i = 0; i < A6_CHARGER_SAMPLES; i++) {
		ret = a6_charger_read(0x45, &a6_charger_current[i]);
		if (ret) goto cleanup;
		if (i + 1 < A6_CHARGER_SAMPLES) msleep(1000);
	}
cleanup:
	/* Always restore all three writable bytes in reverse order. */
	if (wrote_1b) {
		a6_power_recover();
		cr = a6_power_set(0x1b, a6_charger_before[0]);
		if (cr && !a6_charger_cleanup_result) a6_charger_cleanup_result = cr;
		a6_power_recover();
	}
	if (wrote_3f) {
		a6_power_recover();
		cr = a6_power_set(0x3f, a6_charger_before[1]);
		if (cr && !a6_charger_cleanup_result) a6_charger_cleanup_result = cr;
		a6_power_recover();
	}
	if (wrote_43) {
		a6_power_recover();
		cr = a6_power_set(0x43, a6_charger_before[2]);
		if (cr && !a6_charger_cleanup_result) a6_charger_cleanup_result = cr;
		a6_power_recover();
	}
	cr = a6_charger_snapshot(a6_charger_after);
	if (cr && !a6_charger_cleanup_result) a6_charger_cleanup_result = cr;
	a6_charger_restored = !a6_charger_cleanup_result &&
		!memcmp(a6_charger_before, a6_charger_after, 5) && a6_power_recover();
	if (!ret && !a6_charger_restored) ret = -EUCLEAN;
	a6_charger_result = ret;
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}
static struct kobj_attribute a6_charger_status_attr = __ATTR(status, 0400, a6_charger_status_show, NULL);
static struct kobj_attribute a6_charger_observe_attr = __ATTR(observe, 0200, NULL, a6_charger_observe_store);
static struct kobj_attribute a6_charger_prove_attr = __ATTR(prove, 0200, NULL, a6_charger_prove_store);
static struct attribute *a6_charger_attrs[] = { &a6_charger_status_attr.attr, &a6_charger_observe_attr.attr, &a6_charger_prove_attr.attr, NULL };
static const struct attribute_group a6_charger_group = { .name = "a6_charger", .attrs = a6_charger_attrs };
static int __init a6_charger_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c) return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_charger_group);
}
late_initcall(a6_charger_init);

// SPDX-License-Identifier: GPL-2.0-only
/* n42 grape-clk channel2 observer. No PWM configuration or PMU rail writes.
 * arm-io ranges map03500000 to33500000; logical PWM gate2c -> index49.
 */
#define A6_TOUCH_PWM_BASE 0x33500000
#define A6_TOUCH_PWM_GATE 0x124
static void __iomem *a6_touch_pwm;
static bool a6_pwm_attempted;
static int a6_pwm_result;
static u32 a6_pwm_before, a6_pwm_after;

static ssize_t a6_pwm_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	u32 gate;
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	gate = readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE);
	n = sysfs_emit(buf, "A6_TOUCH_CLOCK_V1\npwm_gate=%08x attempted=%u result=%d before=%08x after=%08x\n",
		gate, a6_pwm_attempted, a6_pwm_result, a6_pwm_before, a6_pwm_after);
	if (gate != U32_MAX && (gate & 0xff) == 0xff &&
	    readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE) == gate)
		n += sysfs_emit_at(buf, n, "channel=2 pwm_10=%08x pwm_14=%08x pwm_20=%08x\n",
			readl(a6_touch_pwm + 0x10), readl(a6_touch_pwm + 0x14),
			readl(a6_touch_pwm + 0x20));
	else
		n += sysfs_emit_at(buf, n, "pwm_registers=skipped_clock_not_ready\n");
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_pwm_enable_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	u32 gate, check;
	int ret = 0;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "enable-pwm-gate"))
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_pwm_attempted) {
		ret = -EALREADY;
		goto out;
	}
	gate = readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE);
	if (gate == U32_MAX || gate != readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE) ||
	    ((gate & 0xff) != 0 && (gate & 0xff) != 0xff)) {
		ret = -EBUSY;
		goto out;
	}
	a6_pwm_attempted = true;
	a6_pwm_before = gate;
	if ((gate & 0xff) != 0xff) {
		writel(gate | 0xf, a6_touch_pmgr + A6_TOUCH_PWM_GATE);
		ret = readl_poll_timeout(a6_touch_pmgr + A6_TOUCH_PWM_GATE, check,
			check != U32_MAX && (check & 0xff) == 0xff, 10, 100000);
	}
	a6_pwm_after = readl(a6_touch_pmgr + A6_TOUCH_PWM_GATE);
	a6_pwm_result = ret;
	pr_info("a6-touch: PWM gate %08x -> %08x result=%d; no PWM/GPIO/PMU writes\n",
		gate, a6_pwm_after, ret);
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}
static struct kobj_attribute a6_pwm_status_attr =
	__ATTR(status, 0400, a6_pwm_status_show, NULL);
static struct kobj_attribute a6_pwm_enable_attr =
	__ATTR(enable_gate, 0200, NULL, a6_pwm_enable_store);
static struct attribute *a6_pwm_attrs[] = {
	&a6_pwm_status_attr.attr, &a6_pwm_enable_attr.attr, NULL,
};
static const struct attribute_group a6_pwm_group = {
	.name = "a6_touch_clock", .attrs = a6_pwm_attrs,
};
static int __init a6_touch_clock_init(void)
{
	int ret;
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_pmgr)
		return -ENODEV;
	a6_touch_pwm = ioremap(A6_TOUCH_PWM_BASE, 0x1000);
	if (!a6_touch_pwm)
		return -ENOMEM;
	ret = sysfs_create_group(firmware_kobj, &a6_pwm_group);
	if (ret) {
		iounmap(a6_touch_pwm);
		a6_touch_pwm = NULL;
	}
	return ret;
}
late_initcall(a6_touch_clock_init);

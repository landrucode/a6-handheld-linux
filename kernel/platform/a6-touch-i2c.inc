// SPDX-License-Identifier: GPL-2.0-only
/* Fixed n42 I2C0 observer. No controller, GPIO or PMU writes.
 * arm-io03200000 ->33200000; logical gate29 -> index46.
 * Only stock-polled status14, divider1c and version28 are read.
 */
#define A6_TOUCH_I2C_BASE 0x33200000
#define A6_TOUCH_I2C_GATE 0x118
static void __iomem *a6_touch_i2c;
static bool a6_i2c_attempted;
static int a6_i2c_result;
static u32 a6_i2c_before, a6_i2c_after;

static ssize_t a6_i2c_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	u32 gate;
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	gate = readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE);
	n = sysfs_emit(buf, "A6_TOUCH_I2C_V1\ni2c_gate=%08x attempted=%u result=%d before=%08x after=%08x\n",
		gate, a6_i2c_attempted, a6_i2c_result, a6_i2c_before, a6_i2c_after);
	n += sysfs_emit_at(buf, n, "sda_gpio58=%08x scl_gpio59=%08x\n",
		readl(a6_touch_gpio + 0xe8), readl(a6_touch_gpio + 0xec));
	if (gate != U32_MAX && (gate & 0xff) == 0xff &&
	    readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE) == gate)
		n += sysfs_emit_at(buf, n, "i2c_14=%08x i2c_1c=%08x i2c_28=%08x\n",
			readl(a6_touch_i2c + 0x14), readl(a6_touch_i2c + 0x1c),
			readl(a6_touch_i2c + 0x28));
	else
		n += sysfs_emit_at(buf, n, "i2c_registers=skipped_clock_not_ready\n");
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_i2c_enable_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	u32 gate, check;
	int ret = 0;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "enable-i2c-gate"))
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_i2c_attempted) {
		ret = -EALREADY;
		goto out;
	}
	gate = readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE);
	if (gate == U32_MAX || gate != readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE) ||
	    ((gate & 0xff) != 0 && (gate & 0xff) != 0xff)) {
		ret = -EBUSY;
		goto out;
	}
	a6_i2c_attempted = true;
	a6_i2c_before = gate;
	if ((gate & 0xff) != 0xff) {
		writel(gate | 0xf, a6_touch_pmgr + A6_TOUCH_I2C_GATE);
		ret = readl_poll_timeout(a6_touch_pmgr + A6_TOUCH_I2C_GATE, check,
			check != U32_MAX && (check & 0xff) == 0xff, 10, 100000);
	}
	a6_i2c_after = readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE);
	a6_i2c_result = ret;
	pr_info("a6-touch: I2C gate %08x -> %08x result=%d; no I2C/GPIO/PMU writes\n",
		gate, a6_i2c_after, ret);
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}
static struct kobj_attribute a6_i2c_status_attr =
	__ATTR(status, 0400, a6_i2c_status_show, NULL);
static struct kobj_attribute a6_i2c_enable_attr =
	__ATTR(enable_gate, 0200, NULL, a6_i2c_enable_store);
static struct attribute *a6_i2c_attrs[] = {
	&a6_i2c_status_attr.attr, &a6_i2c_enable_attr.attr, NULL,
};
static const struct attribute_group a6_i2c_group = {
	.name = "a6_touch_i2c", .attrs = a6_i2c_attrs,
};
static int __init a6_touch_i2c_init(void)
{
	int ret;
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_pmgr)
		return -ENODEV;
	a6_touch_i2c = ioremap(A6_TOUCH_I2C_BASE, 0x1000);
	if (!a6_touch_i2c)
		return -ENOMEM;
	ret = sysfs_create_group(firmware_kobj, &a6_i2c_group);
	if (ret) {
		iounmap(a6_touch_i2c);
		a6_touch_i2c = NULL;
	}
	return ret;
}
late_initcall(a6_touch_i2c_init);

// SPDX-License-Identifier: GPL-2.0-only
/* N42 stock DWI WLED update, bounded and reversible. The already-lit LM3534
 * enable state is left alone. Caller holds the shared D1972/touch lock.
 */
#include <linux/capability.h>
#include <linux/delay.h>
#include <linux/ktime.h>
#define A6_BL_DWI_BASE 0x3f700000 /* arm-io ranges: 0x30000000 + 0x0f700000 */
#define A6_BL_PMGR_BASE 0x3f101000
#define A6_BL_DWI_GATE 0x134 /* N42 DWI logical 0x7f -> PMGR index 0x4d */
#define A6_BL_COMMAND 0x10
#define A6_BL_DATA 0x14
#define A6_BL_WLED_COMMAND 0x71
#define A6_BL_VERSION1_PREFIX 0xa0000000U
static void __iomem *a6_bl_dwi, *a6_bl_pmgr;
static bool a6_bl_attempted, a6_bl_restored;
static int a6_bl_result, a6_bl_cleanup_result;
static u32 a6_bl_gate, a6_bl_gate_before, a6_bl_gate_after;
static u32 a6_bl_before_cmd, a6_bl_before_data;
static u32 a6_bl_dim_cmd, a6_bl_dim_data, a6_bl_after_cmd, a6_bl_after_data;

static int a6_bl_wait_done(void)
{
	u32 state;
	unsigned int i;
	u64 deadline = ktime_get_ns() + 20000000;

	for (i = 0; i < 1000000; i++) {
		state = readl(a6_bl_dwi + A6_BL_COMMAND);
		if (state == U32_MAX)
			return -EIO;
		if (!(state & 1))
			return 0;
		if (ktime_get_ns() >= deadline)
			break;
		cpu_relax();
	}
	return -ETIMEDOUT;
}

static ssize_t a6_bl_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	a6_bl_gate = readl(a6_bl_pmgr + A6_BL_DWI_GATE);
	n = sysfs_emit(buf,
		"A6_BACKLIGHT_DWI_TRIAL_V4\n"
		"attempted=%u result=%d cleanup_result=%d restored=%u gate=%08x gate_before=%08x gate_after=%08x\n"
		"before_cmd=%08x before_data=%08x dim_cmd=%08x dim_data=%08x after_cmd=%08x after_data=%08x\n",
		a6_bl_attempted, a6_bl_result, a6_bl_cleanup_result,
		a6_bl_restored, a6_bl_gate, a6_bl_gate_before,
		a6_bl_gate_after, a6_bl_before_cmd,
		a6_bl_before_data, a6_bl_dim_cmd, a6_bl_dim_data,
		a6_bl_after_cmd, a6_bl_after_data);
	if ((a6_bl_gate & 0xff) == 0xff) {
		n += sysfs_emit_at(buf, n, "live_cmd=%08x live_data=%08x\n",
			readl(a6_bl_dwi + A6_BL_COMMAND),
			readl(a6_bl_dwi + A6_BL_DATA));
	}
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_bl_prove_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	u32 level, gate_check;
	int ret = 0, cr;
	bool wrote = false, gate_enabled = false, data_restored = false;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!sysfs_streq(buf, "dim-half-5s-and-restore")) return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_bl_attempted) { ret = -EALREADY; goto out; }
	a6_bl_attempted = true;
	a6_bl_gate_before = readl(a6_bl_pmgr + A6_BL_DWI_GATE);
	gate_check = readl(a6_bl_pmgr + A6_BL_DWI_GATE);
	if (a6_bl_gate_before != gate_check || gate_check == U32_MAX ||
	    ((gate_check & 0xff) != 0 && (gate_check & 0xff) != 0xff)) {
		ret = -EBUSY; goto out;
	}
	if ((gate_check & 0xff) == 0) {
		gate_enabled = true;
		writel(gate_check | 0xf, a6_bl_pmgr + A6_BL_DWI_GATE);
		cr = readl_poll_timeout(a6_bl_pmgr + A6_BL_DWI_GATE,
			gate_check, gate_check != U32_MAX &&
			(gate_check & 0xff) == 0xff, 10, 100000);
		if (cr) { ret = cr; goto cleanup_gate; }
	}
	a6_bl_before_cmd = readl(a6_bl_dwi + A6_BL_COMMAND);
	a6_bl_before_data = readl(a6_bl_dwi + A6_BL_DATA);
	level = a6_bl_before_data & 0x7ff;
	if (a6_bl_before_cmd != 0x70 ||
	    (a6_bl_before_data & ~0x7ffU) != A6_BL_VERSION1_PREFIX ||
	    level < 64) { ret = -EPROTO; goto cleanup_gate; }
	a6_bl_dim_data = A6_BL_VERSION1_PREFIX | (level / 2);
	wrote = true;
	writel(a6_bl_dim_data, a6_bl_dwi + A6_BL_DATA);
	writel(A6_BL_WLED_COMMAND, a6_bl_dwi + A6_BL_COMMAND);
	ret = a6_bl_wait_done();
	a6_bl_dim_cmd = readl(a6_bl_dwi + A6_BL_COMMAND);
	if (!ret && a6_bl_dim_cmd != 0x70) ret = -EIO;
	if (!ret) msleep(5000);
	if (wrote) {
		/* Restore the exact prior level even if the dim command timed out. */
		writel(a6_bl_before_data, a6_bl_dwi + A6_BL_DATA);
		writel(A6_BL_WLED_COMMAND, a6_bl_dwi + A6_BL_COMMAND);
		cr = a6_bl_wait_done();
		if (cr) a6_bl_cleanup_result = cr;
		a6_bl_after_cmd = readl(a6_bl_dwi + A6_BL_COMMAND);
		a6_bl_after_data = readl(a6_bl_dwi + A6_BL_DATA);
		data_restored = !a6_bl_cleanup_result &&
			a6_bl_after_cmd == a6_bl_before_cmd &&
			a6_bl_after_data == a6_bl_before_data;
		if (!ret && !data_restored) ret = -EUCLEAN;
	}
cleanup_gate:
	if (gate_enabled) {
		writel(a6_bl_gate_before, a6_bl_pmgr + A6_BL_DWI_GATE);
		cr = readl_poll_timeout(a6_bl_pmgr + A6_BL_DWI_GATE,
			gate_check, gate_check == a6_bl_gate_before,
			10, 100000);
		if (cr && !a6_bl_cleanup_result) a6_bl_cleanup_result = cr;
	}
	a6_bl_gate_after = readl(a6_bl_pmgr + A6_BL_DWI_GATE);
	a6_bl_restored = !a6_bl_cleanup_result &&
		a6_bl_gate_after == a6_bl_gate_before &&
		(!wrote || data_restored);
	if (!ret && !a6_bl_restored) ret = -EUCLEAN;
out:
	a6_bl_result = ret;
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_bl_status_attr =
	__ATTR(status, 0400, a6_bl_status_show, NULL);
static struct kobj_attribute a6_bl_prove_attr =
	__ATTR(prove, 0200, NULL, a6_bl_prove_store);
static struct attribute *a6_bl_attrs[] = {
	&a6_bl_status_attr.attr, &a6_bl_prove_attr.attr, NULL,
};
static const struct attribute_group a6_bl_group = {
	.name = "a6_backlight_trial", .attrs = a6_bl_attrs,
};
static int __init a6_bl_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap")) return -ENODEV;
	a6_bl_dwi = ioremap(A6_BL_DWI_BASE, 0x1000);
	a6_bl_pmgr = ioremap(A6_BL_PMGR_BASE, 0x1000);
	if (!a6_bl_dwi || !a6_bl_pmgr) return -ENOMEM;
	return sysfs_create_group(firmware_kobj, &a6_bl_group);
}
late_initcall(a6_bl_init);

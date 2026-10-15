// SPDX-License-Identifier: GPL-2.0-only
/* Fixed n42 common-page PMU reads. No PMU data/bank/rail writes.
 * Stock D1972 uses address74; S5L8940XI2C shifts once, command FIFO at0.
 * Common registers below5e are accessible in either bank0/1.
 */
#include <linux/delay.h>
#define A6_PMU_XIP (1U << 28)
#define A6_PMU_XEN (1U << 27)
#define A6_PMU_MRNE (1U << 19)
#define A6_PMU_MTE (1U << 16)
#define A6_PMU_ERRORS ((1U<<25)|(1U<<24)|(1U<<23)|(1U<<22)|(1U<<21)|(1U<<6))
static bool a6_pmu_attempted, a6_pmu_idle, a6_pmu_config_ok, a6_pmu_bank_ok;
static int a6_pmu_result;
static unsigned int a6_pmu_received, a6_pmu_polls;
static u8 a6_pmu_bytes[5];
static u32 a6_pmu_before_status, a6_pmu_before_mask, a6_pmu_before_control, a6_pmu_before_revision;
static u32 a6_pmu_status[5], a6_pmu_final_status, a6_pmu_final_control;

static int a6_pmu_read_byte(u8 reg, unsigned int index)
{
	u32 status, data;
	unsigned int poll;
	/* Stock mode1 puts STOP after the pointer byte and after the read.
	 * FIFO sequence contains one address byte, never a PMU data write.
	 */
	status = readl(a6_touch_i2c + 0x14);
	if (status == U32_MAX || (status & (A6_PMU_XIP|A6_PMU_ERRORS|A6_PMU_MRNE)) ||
	    !(status & A6_PMU_MTE))
		return -EBUSY;
	writel(status, a6_touch_i2c + 0x14); /* W1C inherited events. */
	writel(0x1e8, a6_touch_i2c);
	writel(0x200 | reg, a6_touch_i2c);
	writel(0x1e9, a6_touch_i2c);
	writel(0x601, a6_touch_i2c);
	for (poll = 0; poll < 10000; poll++) {
		status = readl(a6_touch_i2c + 0x14);
		a6_pmu_status[index] = status;
		a6_pmu_polls++;
		if (status == U32_MAX)
			return -EIO;
		if (status & A6_PMU_ERRORS)
			return (status & (1U<<21)) ? -ENXIO : -EIO;
		if (!(status & A6_PMU_XIP) &&
		    (status & (A6_PMU_XEN|A6_PMU_MTE|A6_PMU_MRNE)) ==
		    (A6_PMU_XEN|A6_PMU_MTE|A6_PMU_MRNE))
			break;
		udelay(10);
	}
	if (poll == 10000)
		return -ETIMEDOUT;
	data = readl(a6_touch_i2c + 4); /* Exactly one RX read per completed byte. */
	if (data & ~0xffU)
		return -ENODATA;
	a6_pmu_bytes[index] = data;
	a6_pmu_received++;
	writel(A6_PMU_XEN, a6_touch_i2c + 0x14);
	return 0;
}

static ssize_t a6_pmu_result_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, "A6_TOUCH_PMU_READ_V1\nattempted=%u result=%d received=%u polls=%u controller_idle=%u config_restored=%u bank_unchanged=%u\n",
		a6_pmu_attempted, a6_pmu_result, a6_pmu_received, a6_pmu_polls,
		a6_pmu_idle, a6_pmu_config_ok, a6_pmu_bank_ok);
	n += sysfs_emit_at(buf, n, "before_status=%08x before_mask=%08x before_control=%08x before_revision=%08x\n",
		a6_pmu_before_status, a6_pmu_before_mask, a6_pmu_before_control, a6_pmu_before_revision);
	n += sysfs_emit_at(buf, n, "bank_before=%02x id_00=%02x enable_22=%02x enable_23=%02x bank_after=%02x\n",
		a6_pmu_bytes[0], a6_pmu_bytes[1], a6_pmu_bytes[2], a6_pmu_bytes[3], a6_pmu_bytes[4]);
	n += sysfs_emit_at(buf, n, "status=%08x,%08x,%08x,%08x,%08x final_status=%08x final_control=%08x\n",
		a6_pmu_status[0], a6_pmu_status[1], a6_pmu_status[2], a6_pmu_status[3], a6_pmu_status[4],
		a6_pmu_final_status, a6_pmu_final_control);
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_pmu_run_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	static const u8 regs[] = {0x1e, 0, 0x22, 0x23, 0x1e};
	u32 gate, status;
	unsigned int i;
	int ret = 0;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "read-pmu-common"))
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_pmu_attempted) { ret = -EALREADY; goto out; }
	if (!a6_touch_i2c) { ret = -ENODEV; goto out; }
	gate = readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE);
	if (gate != 0x2ff || gate != readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE)) {
		ret = -EBUSY; goto out;
	}
	a6_pmu_before_revision = readl(a6_touch_i2c + 0x28);
	a6_pmu_before_control = readl(a6_touch_i2c + 0x1c);
	a6_pmu_before_mask = readl(a6_touch_i2c + 0x18);
	a6_pmu_before_status = readl(a6_touch_i2c + 0x14);
	if (readl(a6_touch_gpio + 0xe8) != 0x221 || readl(a6_touch_gpio + 0xec) != 0x221 ||
	    a6_pmu_before_revision != 1 || a6_pmu_before_control != 0x104 ||
	    a6_pmu_before_mask != 0 || a6_pmu_before_status != 0x08010100) {
		ret = -EBUSY; goto out;
	}
	a6_pmu_attempted = true;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_pmu_read_byte(regs[i], i);
		if (ret) break;
		if (!i && a6_pmu_bytes[0] > 1) { ret = -EPROTO; break; }
	}
	a6_pmu_bank_ok = a6_pmu_received == 5 && a6_pmu_bytes[0] == a6_pmu_bytes[4];
	if (!ret && !a6_pmu_bank_ok) ret = -EPROTO;
	/* Upstream PA Semi/Apple recovery for rev<6: reset FIFOs, keep divider4.
	 * Never reset the PMU or change pins/gates. Status events are acknowledged,
	 * not restored bit-for-bit. Stop on failure; no retry of bus operations.
	 */
	if (ret) {
		writel(0x704, a6_touch_i2c + 0x1c);
		udelay(10);
		writel(0x104, a6_touch_i2c + 0x1c);
	}
	status = readl(a6_touch_i2c + 0x14);
	if (status != U32_MAX) writel(status, a6_touch_i2c + 0x14);
	a6_pmu_final_status = readl(a6_touch_i2c + 0x14);
	a6_pmu_final_control = readl(a6_touch_i2c + 0x1c);
	a6_pmu_idle = a6_pmu_final_status != U32_MAX &&
		!(a6_pmu_final_status & (A6_PMU_XIP|A6_PMU_ERRORS|A6_PMU_MRNE)) &&
		(a6_pmu_final_status & A6_PMU_MTE);
	a6_pmu_config_ok = a6_pmu_final_control == 0x104 &&
		readl(a6_touch_i2c + 0x18) == 0 &&
		readl(a6_touch_pmgr + A6_TOUCH_I2C_GATE) == gate &&
		readl(a6_touch_gpio + 0xe8) == 0x221 && readl(a6_touch_gpio + 0xec) == 0x221;
	if (!a6_pmu_idle || !a6_pmu_config_ok) ret = -EUCLEAN;
	a6_pmu_result = ret;
out:
	if (!a6_pmu_attempted) a6_pmu_result = ret;
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}
static struct kobj_attribute a6_pmu_result_attr =
	__ATTR(result, 0400, a6_pmu_result_show, NULL);
static struct kobj_attribute a6_pmu_run_attr =
	__ATTR(run, 0200, NULL, a6_pmu_run_store);
static struct attribute *a6_pmu_attrs[] = { &a6_pmu_result_attr.attr, &a6_pmu_run_attr.attr, NULL };
static const struct attribute_group a6_pmu_group = { .name = "a6_touch_pmu", .attrs = a6_pmu_attrs };
static int __init a6_touch_pmu_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c) return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_pmu_group);
}
late_initcall(a6_touch_pmu_init);

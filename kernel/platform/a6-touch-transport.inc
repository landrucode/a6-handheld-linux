// SPDX-License-Identifier: GPL-2.0-only
/* Transitional n42-only transport observation. No arbitrary MMIO interface.
 * SPI1 logical gate 0x1b -> device-clocks index 0x3a -> PMGR +0xe8.
 * GPIO pin encoding and stride verified in the matching stock GPIO driver.
 * There are NO GPIO, SPI, reset, PMU, firmware or storage writes here.
 * The only write is an explicit root request to enable the SPI1 PMGR gate.
 */
#include <linux/capability.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/kobject.h>
#include <linux/mutex.h>
#include <linux/sysfs.h>

#define A6_TOUCH_PMGR_BASE 0x3f101000
#define A6_TOUCH_GPIO_BASE 0x3fa00000
#define A6_TOUCH_SPI_BASE  0x32100000
#define A6_TOUCH_GATE     0xe8
#define A6_TOUCH_CS       0x0c4 /* port6 pin1, linear49 */
#define A6_TOUCH_RESET    0x39c /* port28 pin7, linear231 */
#define A6_TOUCH_ATN      0x324 /* interrupt201, linear201: mapping to verify */

static void __iomem *a6_touch_pmgr, *a6_touch_gpio, *a6_touch_spi;
static DEFINE_MUTEX(a6_touch_lock);
static bool a6_touch_clock_attempted;
static int a6_touch_clock_result;
static u32 a6_touch_gate_before, a6_touch_gate_after;

static ssize_t a6_touch_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	/* Do not read RXDATA (0x20), which consumes FIFO entries. */
	static const u32 offsets[] = { 0, 4, 8, 0xc, 0x30, 0x34, 0x38, 0x4c };
	u32 gate, cs, reset, atn;
	ssize_t used;
	unsigned int i;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	gate = readl(a6_touch_pmgr + A6_TOUCH_GATE);
	cs = readl(a6_touch_gpio + A6_TOUCH_CS);
	reset = readl(a6_touch_gpio + A6_TOUCH_RESET);
	atn = readl(a6_touch_gpio + A6_TOUCH_ATN);
	used = sysfs_emit(buf,
		"A6_TOUCH_TRANSPORT_V1\n"
		"spi1_gate=%08x cs_gpio49=%08x reset_gpio231=%08x atn_candidate201=%08x\n"
		"clock_attempted=%u clock_result=%d gate_before=%08x gate_after=%08x\n",
		gate, cs, reset, atn, a6_touch_clock_attempted,
		a6_touch_clock_result, a6_touch_gate_before, a6_touch_gate_after);
	/* A gated APB read can return a stale bus value on this platform.
	 * Never touch SPI registers unless request and acknowledgement are ON.
	 */
	if (gate != U32_MAX && (gate & 0xff) == 0xff &&
	    readl(a6_touch_pmgr + A6_TOUCH_GATE) == gate) {
		for (i = 0; i < ARRAY_SIZE(offsets); i++)
			used += sysfs_emit_at(buf, used, "spi_%02x=%08x\n",
				offsets[i], readl(a6_touch_spi + offsets[i]));
	} else {
		used += sysfs_emit_at(buf, used, "spi_registers=skipped_clock_not_ready\n");
	}
	mutex_unlock(&a6_touch_lock);
	return used;
}

static ssize_t a6_touch_enable_clock_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	u32 before, check;
	int ret = 0;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "enable-spi1"))
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_touch_clock_attempted) {
		ret = a6_touch_clock_result;
		goto out;
	}
	before = readl(a6_touch_pmgr + A6_TOUCH_GATE);
	/* Reject unstable/in-transition or unrecognized gate states. */
	check = readl(a6_touch_pmgr + A6_TOUCH_GATE);
	if (before != check || before == U32_MAX ||
	    ((before & 0xff) != 0 && (before & 0xff) != 0xff)) {
		ret = -EBUSY;
		goto out;
	}
	a6_touch_clock_attempted = true;
	a6_touch_gate_before = before;
	if ((before & 0xff) != 0xff) {
		writel(before | 0xf, a6_touch_pmgr + A6_TOUCH_GATE);
		ret = readl_poll_timeout(a6_touch_pmgr + A6_TOUCH_GATE, check,
				check != U32_MAX && (check & 0xff) == 0xff,
				10, 100000);
	}
	a6_touch_gate_after = readl(a6_touch_pmgr + A6_TOUCH_GATE);
	a6_touch_clock_result = ret;
	pr_info("a6-touch: SPI1 gate %08x -> %08x result=%d; no SPI/GPIO writes\n",
		before, a6_touch_gate_after, ret);
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_touch_status_attr =
	__ATTR(status, 0400, a6_touch_status_show, NULL);
static struct kobj_attribute a6_touch_clock_attr =
	__ATTR(enable_clock, 0200, NULL, a6_touch_enable_clock_store);
static struct attribute *a6_touch_attrs[] = {
	&a6_touch_status_attr.attr, &a6_touch_clock_attr.attr, NULL,
};
static const struct attribute_group a6_touch_group = {
	.name = "a6_touch_transport", .attrs = a6_touch_attrs,
};

static int __init a6_touch_transport_init(void)
{
	int ret;

	if (!of_machine_is_compatible("apple,n42ap"))
		return -ENODEV;
	a6_touch_pmgr = ioremap(A6_TOUCH_PMGR_BASE, 0x1000);
	a6_touch_gpio = ioremap(A6_TOUCH_GPIO_BASE, 0x1000);
	a6_touch_spi = ioremap(A6_TOUCH_SPI_BASE, 0x1000);
	if (!a6_touch_pmgr || !a6_touch_gpio || !a6_touch_spi) {
		ret = -ENOMEM;
		goto fail;
	}
	ret = sysfs_create_group(firmware_kobj, &a6_touch_group);
	if (ret)
		goto fail;
	pr_info("a6-touch: root-only transport observer ready; hardware untouched\n");
	return 0;
fail:
	if (a6_touch_spi)
		iounmap(a6_touch_spi);
	if (a6_touch_gpio)
		iounmap(a6_touch_gpio);
	if (a6_touch_pmgr)
		iounmap(a6_touch_pmgr);
	a6_touch_spi = NULL;
	a6_touch_gpio = NULL;
	a6_touch_pmgr = NULL;
	return ret;
}
late_initcall(a6_touch_transport_init);

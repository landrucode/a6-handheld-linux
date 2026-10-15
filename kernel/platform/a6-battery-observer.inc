// SPDX-License-Identifier: GPL-2.0-only
/* N42 UART5/HDQ observer. UART5 logical gate 0x24 maps through the stock
 * device-clocks record to PMGR index 0x43, offset 0x10c. GPIO44 is the
 * stock UART5 TX/HDQ pin. No UART FIFO, gauge, charger or PMU access occurs.
 * The only write is an explicit root request to enable the UART5 clock gate.
 */
#include <linux/capability.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/kobject.h>
#include <linux/mutex.h>
#include <linux/sysfs.h>

#define A6_BATTERY_PMGR_BASE 0x3f101000
#define A6_BATTERY_GPIO_BASE 0x3fa00000
#define A6_BATTERY_UART_BASE 0x32a00000
#define A6_BATTERY_UART_GATE 0x10c
#define A6_BATTERY_GPIO44    0x0b0

static void __iomem *a6_battery_pmgr, *a6_battery_gpio, *a6_battery_uart;
static DEFINE_MUTEX(a6_battery_lock);
static bool a6_battery_clock_attempted;
static int a6_battery_clock_result;
static u32 a6_battery_gate_before, a6_battery_gate_after;

static ssize_t a6_battery_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	/* Configuration registers only. Never read TX/RX data (0x20/0x24) or
	 * status/event registers (0x10..0x1c), whose side effects are unproven.
	 */
	static const u32 offsets[] = { 0, 4, 8, 0xc, 0x28, 0x2c };
	u32 gate, gpio44;
	ssize_t used;
	unsigned int i;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_battery_lock);
	gate = readl(a6_battery_pmgr + A6_BATTERY_UART_GATE);
	gpio44 = readl(a6_battery_gpio + A6_BATTERY_GPIO44);
	used = sysfs_emit(buf,
		"A6_BATTERY_OBSERVER_V1\n"
		"uart5_gate=%08x gpio44=%08x clock_attempted=%u clock_result=%d gate_before=%08x gate_after=%08x\n",
		gate, gpio44, a6_battery_clock_attempted, a6_battery_clock_result,
		a6_battery_gate_before, a6_battery_gate_after);
	if (gate != U32_MAX && (gate & 0xff) == 0xff &&
	    readl(a6_battery_pmgr + A6_BATTERY_UART_GATE) == gate) {
		for (i = 0; i < ARRAY_SIZE(offsets); i++)
			used += sysfs_emit_at(buf, used, "uart5_%02x=%08x\n",
				offsets[i], readl(a6_battery_uart + offsets[i]));
	} else {
		used += sysfs_emit_at(buf, used,
			"uart5_registers=skipped_clock_not_ready\n");
	}
	mutex_unlock(&a6_battery_lock);
	return used;
}

static ssize_t a6_battery_enable_clock_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	u32 before, check;
	int ret = 0;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "enable-uart5"))
		return -EINVAL;
	mutex_lock(&a6_battery_lock);
	if (a6_battery_clock_attempted) {
		ret = a6_battery_clock_result;
		goto out;
	}
	before = readl(a6_battery_pmgr + A6_BATTERY_UART_GATE);
	check = readl(a6_battery_pmgr + A6_BATTERY_UART_GATE);
	if (before != check || before == U32_MAX ||
	    ((before & 0xff) != 0 && (before & 0xff) != 0xff)) {
		ret = -EBUSY;
		goto out;
	}
	a6_battery_clock_attempted = true;
	a6_battery_gate_before = before;
	if ((before & 0xff) != 0xff) {
		writel(before | 0xf, a6_battery_pmgr + A6_BATTERY_UART_GATE);
		ret = readl_poll_timeout(a6_battery_pmgr + A6_BATTERY_UART_GATE,
			check, check != U32_MAX && (check & 0xff) == 0xff,
			10, 100000);
	}
	a6_battery_gate_after = readl(a6_battery_pmgr + A6_BATTERY_UART_GATE);
	a6_battery_clock_result = ret;
	pr_info("a6-battery: UART5 gate %08x -> %08x result=%d; no UART/GPIO/PMU writes\n",
		before, a6_battery_gate_after, ret);
out:
	mutex_unlock(&a6_battery_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_battery_status_attr =
	__ATTR(status, 0400, a6_battery_status_show, NULL);
static struct kobj_attribute a6_battery_clock_attr =
	__ATTR(enable_clock, 0200, NULL, a6_battery_enable_clock_store);
static struct attribute *a6_battery_attrs[] = {
	&a6_battery_status_attr.attr, &a6_battery_clock_attr.attr, NULL,
};
static const struct attribute_group a6_battery_group = {
	.name = "a6_battery_observer", .attrs = a6_battery_attrs,
};

static int __init a6_battery_observer_init(void)
{
	int ret;

	if (!of_machine_is_compatible("apple,n42ap"))
		return -ENODEV;
	a6_battery_pmgr = ioremap(A6_BATTERY_PMGR_BASE, 0x1000);
	a6_battery_gpio = ioremap(A6_BATTERY_GPIO_BASE, 0x1000);
	a6_battery_uart = ioremap(A6_BATTERY_UART_BASE, 0x1000);
	if (!a6_battery_pmgr || !a6_battery_gpio || !a6_battery_uart) {
		ret = -ENOMEM;
		goto fail;
	}
	ret = sysfs_create_group(firmware_kobj, &a6_battery_group);
	if (ret)
		goto fail;
	pr_info("a6-battery: root-only UART5/HDQ observer ready; gauge and charger untouched\n");
	return 0;
fail:
	if (a6_battery_uart)
		iounmap(a6_battery_uart);
	if (a6_battery_gpio)
		iounmap(a6_battery_gpio);
	if (a6_battery_pmgr)
		iounmap(a6_battery_pmgr);
	a6_battery_uart = NULL;
	a6_battery_gpio = NULL;
	a6_battery_pmgr = NULL;
	return ret;
}
late_initcall(a6_battery_observer_init);

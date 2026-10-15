// SPDX-License-Identifier: GPL-2.0-only
/* Passive DWC2 state on the inherited N42 framebuffer. Diagnostic image only.
 * No USB register writes and no second framebuffer mapping.
 */
#include <linux/workqueue.h>
#include <linux/jiffies.h>
#include <linux/capability.h>
#include <linux/kobject.h>
#include <linux/sysfs.h>

static bool a6_usb_screen_enabled = true;
#ifdef A6_USB_RECONNECT_VBUS_LATCH
#include <linux/power_supply.h>
#endif

extern u32 a6_usb_reconnect_trace[];
#ifdef A6_USB_RECONNECT_PHY
static void __iomem *a6_usb_phy_screen_base;
static void __iomem *a6_usb_core_screen_base;
#endif
#ifdef A6_USB_RECONNECT_VBUS_LATCH
static u32 a6_usb_source_trace[9];
static int a6_usb_last_online = -1;
#endif
#ifdef A6_USB_CORE_RESET_TRACE
#ifdef A6_USB_CORE_STAGE_TRACE
extern u32 a6_usb_core_reset_trace[10];
#else
extern u32 a6_usb_core_reset_trace[3];
#endif
#endif
#ifdef A6_USB_RECONNECT_LX_LATCH
extern u32 a6_usb_lx_trace[9];
extern bool a6_usb_lx_snapshot_valid;
#endif

static const u8 a6_usb_hex_font[16][7] = {
	{14,17,19,21,25,17,14}, {4,12,4,4,4,4,14},
	{14,17,1,2,4,8,31}, {30,1,1,14,1,1,30},
	{2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
	{14,16,16,30,17,17,14}, {31,1,2,4,8,8,8},
	{14,17,17,14,17,17,14}, {14,17,17,15,1,1,14},
	{14,17,17,31,17,17,17}, {30,17,17,30,17,17,30},
	{14,17,16,16,16,17,14}, {30,17,17,17,17,17,30},
	{31,16,16,30,16,16,31}, {31,16,16,30,16,16,16},
};

static void a6_usb_screen_digit(unsigned int x, unsigned int y, u8 digit)
{
	u8 row;
	u32 __iomem *fb = (u32 __iomem *)(unsigned long)0xbf7aa000;

	for (row = 0; row < 7; row++) {
		u8 col;
		for (col = 0; col < 5; col++) {
			u32 color = a6_usb_hex_font[digit & 15][row] & (1 << (4 - col)) ?
				0x00ffffff : 0x00000000;
			u8 dy, dx;
			for (dy = 0; dy < 2; dy++)
				for (dx = 0; dx < 2; dx++)
					writel(color, fb + (y + row * 2 + dy) * 640 +
						(x + col * 2 + dx));
		}
	}
}

static void a6_usb_screen_work(struct work_struct *unused);
static DECLARE_DELAYED_WORK(a6_usb_screen_job, a6_usb_screen_work);

static void a6_usb_screen_work(struct work_struct *unused)
{
	u32 __iomem *fb = (u32 __iomem *)(unsigned long)0xbf7aa000;
	unsigned int row;

#ifdef A6_USB_RECONNECT_PHY
	if (a6_usb_phy_screen_base && a6_usb_core_screen_base) {
		WRITE_ONCE(a6_usb_reconnect_trace[9],
			readl(a6_usb_phy_screen_base + 0x1c));
		WRITE_ONCE(a6_usb_reconnect_trace[10],
			readl(a6_usb_phy_screen_base));
		WRITE_ONCE(a6_usb_reconnect_trace[11],
			readl(a6_usb_core_screen_base + 0x00));
		WRITE_ONCE(a6_usb_reconnect_trace[12],
			readl(a6_usb_core_screen_base + 0x08));
		WRITE_ONCE(a6_usb_reconnect_trace[13],
			readl(a6_usb_core_screen_base + 0x14));
		WRITE_ONCE(a6_usb_reconnect_trace[14],
			readl(a6_usb_core_screen_base + 0x18));
		WRITE_ONCE(a6_usb_reconnect_trace[15],
			readl(a6_usb_core_screen_base + 0x804));
		WRITE_ONCE(a6_usb_reconnect_trace[16],
			readl(a6_usb_core_screen_base + 0x808));
		WRITE_ONCE(a6_usb_reconnect_trace[17],
			readl(a6_usb_core_screen_base + 0xb00));
	}
#endif
#ifdef A6_USB_RECONNECT_VBUS_LATCH
	{
		struct power_supply *psy = power_supply_get_by_name("a6-d1972-usb");
		union power_supply_propval val;
		int ret = psy ? power_supply_get_property(psy,
			POWER_SUPPLY_PROP_ONLINE, &val) : -ENODEV;
		if (psy)
			power_supply_put(psy);
		a6_usb_source_trace[7]++;
		if (ret) {
			a6_usb_source_trace[8] = (u32)ret;
		} else {
			int online = !!val.intval;
			a6_usb_source_trace[0] = online;
			if (a6_usb_last_online >= 0 && online != a6_usb_last_online)
				a6_usb_source_trace[1]++;
			a6_usb_last_online = online;
			if (online)
				a6_usb_source_trace[3] = (u32)jiffies;
			else
				a6_usb_source_trace[2] = (u32)jiffies;
			if (a6_usb_core_screen_base &&
			    !!(readl(a6_usb_core_screen_base) & BIT(19)) != online)
				a6_usb_source_trace[4]++;
		}
		if (a6_usb_core_screen_base &&
		    !(readl(a6_usb_core_screen_base) & BIT(19)))
			a6_usb_source_trace[5]++;
		if (a6_usb_phy_screen_base &&
		    readl(a6_usb_phy_screen_base + 0x1c) != 6)
			a6_usb_source_trace[6]++;
	}
#endif

	if (!READ_ONCE(a6_usb_screen_enabled)) goto reschedule;

	for (row = 0; row < 9; row++) {
		u32 value = READ_ONCE(a6_usb_reconnect_trace[row]);
		unsigned int y = 850 + row * 29;
		unsigned int x;
		for (x = 0; x < 21; x++)
			memset_io(fb + (y + x) * 640, 0, 180 * 4);
		a6_usb_screen_digit(10, y, row);
		for (x = 0; x < 8; x++)
			a6_usb_screen_digit(34 + x * 14, y,
				(value >> (28 - x * 4)) & 15);
	}
#if defined(A6_USB_RECONNECT_EP0) || defined(A6_USB_RECONNECT_PHY)
	for (row = 0; row < 9; row++) {
		u32 value = READ_ONCE(a6_usb_reconnect_trace[9 + row]);
		unsigned int y = 850 + row * 29;
		unsigned int x;
		for (x = 0; x < 21; x++)
			memset_io(fb + (y + x) * 640 + 210, 0, 180 * 4);
		a6_usb_screen_digit(210, y, row);
		for (x = 0; x < 8; x++)
			a6_usb_screen_digit(234 + x * 14, y,
				(value >> (28 - x * 4)) & 15);
	}
#endif
#if defined(A6_USB_RECONNECT_VBUS_LATCH) || defined(A6_USB_RECONNECT_LX_LATCH)
	for (row = 0; row < 9; row++) {
#ifdef A6_USB_RECONNECT_LX_LATCH
		u32 value = row == 0 ? READ_ONCE(a6_usb_lx_trace[0]) :
			(smp_load_acquire(&a6_usb_lx_snapshot_valid) ?
			 READ_ONCE(a6_usb_lx_trace[row]) : 0);
#else
		u32 value = a6_usb_source_trace[row];
#ifdef A6_USB_CORE_RESET_TRACE
		if (row == 2)
			value = READ_ONCE(a6_usb_core_reset_trace[0]);
#ifdef A6_USB_CORE_STAGE_TRACE
		else if (row == 3)
			value = READ_ONCE(a6_usb_core_reset_trace[5]);
		else if (row == 5)
			value = READ_ONCE(a6_usb_core_reset_trace[6]);
		else if (row == 6)
			value = READ_ONCE(a6_usb_core_reset_trace[7]);
		else if (row == 7)
			value = READ_ONCE(a6_usb_core_reset_trace[9]);
		else if (row == 8)
			value = READ_ONCE(a6_usb_core_reset_trace[8]);
#else
		else if (row == 6)
			value = READ_ONCE(a6_usb_core_reset_trace[1]);
		else if (row == 8)
			value = READ_ONCE(a6_usb_core_reset_trace[2]);
#endif
#endif
#endif
		unsigned int y = 850 + row * 29;
		unsigned int x;
		for (x = 0; x < 21; x++)
			memset_io(fb + (y + x) * 640 + 410, 0, 180 * 4);
		a6_usb_screen_digit(410, y, row);
		for (x = 0; x < 8; x++)
			a6_usb_screen_digit(434 + x * 14, y,
				(value >> (28 - x * 4)) & 15);
	}
#endif
reschedule:
	schedule_delayed_work(&a6_usb_screen_job, HZ / 2);
}

/* Hide only the painter; passive sampling and USB recovery stay enabled. */
static ssize_t a6_usb_screen_enabled_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%u\n", READ_ONCE(a6_usb_screen_enabled));
}
static ssize_t a6_usb_screen_enabled_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	bool enabled;
	int ret;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	ret = kstrtobool(buf, &enabled);
	if (ret) return ret;
	WRITE_ONCE(a6_usb_screen_enabled, enabled);
	return count;
}
static struct kobj_attribute a6_usb_screen_enabled_attr =
	__ATTR(enabled, 0600, a6_usb_screen_enabled_show, a6_usb_screen_enabled_store);
static struct attribute *a6_usb_screen_attrs[] = {
	&a6_usb_screen_enabled_attr.attr, NULL
};
static const struct attribute_group a6_usb_screen_group = {
	.name = "a6_usb_screen", .attrs = a6_usb_screen_attrs
};

static int __init a6_usb_screen_init(void)
{
	int ret;
	if (!of_machine_is_compatible("apple,n42ap") ||
	    READ_ONCE(a6_fb_base_saved) != 0xbf7aa000 ||
	    READ_ONCE(a6_fb_stride_saved) != 640 * 4 ||
	    !a6_fb_mapping_valid(0xbf7aa000, 640 * 1136 * 4))
		return -ENODEV;
#ifdef A6_USB_RECONNECT_PHY
	a6_usb_phy_screen_base = ioremap(0x36000000, 0x100);
	a6_usb_core_screen_base = ioremap(0x36100000, 0x1000);
	if (!a6_usb_phy_screen_base || !a6_usb_core_screen_base) {
		if (a6_usb_phy_screen_base)
			iounmap(a6_usb_phy_screen_base);
		if (a6_usb_core_screen_base)
			iounmap(a6_usb_core_screen_base);
		return -ENOMEM;
	}
#endif
	ret = sysfs_create_group(firmware_kobj, &a6_usb_screen_group);
	if (ret) {
#ifdef A6_USB_RECONNECT_PHY
		iounmap(a6_usb_phy_screen_base);
		iounmap(a6_usb_core_screen_base);
#endif
		return ret;
	}
	schedule_delayed_work(&a6_usb_screen_job, HZ);
	return 0;
}
late_initcall(a6_usb_screen_init);

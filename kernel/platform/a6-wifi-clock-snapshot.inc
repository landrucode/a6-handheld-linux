// SPDX-License-Identifier: GPL-2.0-only
/* N42 passive, once-per-boot WLAN clock snapshot. No controller/radio writes.
 * Read only stock-polled PMGR controls and the existing shared USB control.
 * Do not read gated EHCI/PHY windows or interrupt-acknowledgement registers.
 */
#include <linux/io.h>
#include <linux/kobject.h>
#include <linux/sysfs.h>

static u32 a6_wifi_clock_values[6];

static ssize_t a6_wifi_clock_snapshot_show(struct kobject *kobj,
                                          struct kobj_attribute *attr,
                                          char *buf)
{
    return sysfs_emit(buf,
        "A6_WIFI_CLOCK_SNAPSHOT_V1 frozen=1 writes=0 "
        "uperf_3f101084=%08x usbreg_3f10109c=%08x "
        "ehci_3f10108c=%08x phy1_3f1002a4=%08x "
        "ehci_secondary_3f1002a8=%08x usb_ctl_3f108000=%08x\n",
        a6_wifi_clock_values[0], a6_wifi_clock_values[1],
        a6_wifi_clock_values[2], a6_wifi_clock_values[3],
        a6_wifi_clock_values[4], a6_wifi_clock_values[5]);
}

static struct kobj_attribute a6_wifi_clock_snapshot_attr =
    __ATTR(status, 0400, a6_wifi_clock_snapshot_show, NULL);
static struct attribute *a6_wifi_clock_snapshot_attrs[] = {
    &a6_wifi_clock_snapshot_attr.attr, NULL
};
static const struct attribute_group a6_wifi_clock_snapshot_group = {
    .name = "a6_wifi_clock_snapshot", .attrs = a6_wifi_clock_snapshot_attrs
};

static int __init a6_wifi_clock_snapshot_init(void)
{
    static const unsigned int offsets[] = {
        0x1084, 0x109c, 0x108c, 0x2a4, 0x2a8
    };
    void __iomem *pmgr, *usb_ctl;
    unsigned int i;

    if (!of_machine_is_compatible("apple,n42ap"))
        return 0;
    pmgr = ioremap(0x3f100000, 0x2000);
    if (!pmgr)
        return -ENOMEM;
    usb_ctl = ioremap(0x3f108000, 0x1000);
    if (!usb_ctl) {
        iounmap(pmgr);
        return -ENOMEM;
    }
    for (i = 0; i < ARRAY_SIZE(offsets); i++)
        a6_wifi_clock_values[i] = readl(pmgr + offsets[i]);
    a6_wifi_clock_values[5] = readl(usb_ctl);
    iounmap(usb_ctl);
    iounmap(pmgr);
    pr_info("A6_WIFI_CLOCK_SNAPSHOT_V1 frozen=1 writes=0 values=%08x/%08x/%08x/%08x/%08x/%08x\n",
        a6_wifi_clock_values[0], a6_wifi_clock_values[1],
        a6_wifi_clock_values[2], a6_wifi_clock_values[3],
        a6_wifi_clock_values[4], a6_wifi_clock_values[5]);
    return sysfs_create_group(firmware_kobj, &a6_wifi_clock_snapshot_group);
}
late_initcall(a6_wifi_clock_snapshot_init);

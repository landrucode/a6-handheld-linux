// SPDX-License-Identifier: GPL-2.0-only
/* One-shot N42 EHCI capability read, with one owned gate and restoration.
 * No EHCI writes, port reset, PHY programming, firmware or radio operations.
 */
#include <linux/iopoll.h>
#include <linux/mutex.h>

static DEFINE_MUTEX(a6_wifi_caps_lock);
static bool a6_wifi_caps_attempted;
static int a6_wifi_caps_result = -EAGAIN, a6_wifi_caps_restore = -EAGAIN;
static u32 a6_wifi_caps_words[4], a6_wifi_caps_before, a6_wifi_caps_after;
static u32 a6_wifi_caps_command, a6_wifi_caps_status;
static unsigned int a6_wifi_caps_gate_writes;

static ssize_t a6_wifi_caps_show(struct kobject *kobj,
                                struct kobj_attribute *attr, char *buf)
{
    ssize_t result;
    mutex_lock(&a6_wifi_caps_lock);
    result = sysfs_emit(buf,
        "A6_WIFI_EHCI_CAPS_V1 attempted=%u result=%d restore=%d gate_writes=%u "
        "controller_writes=0 before=%08x after=%08x caps=%08x/%08x/%08x/%08x "
        "usbcmd=%08x usbsts=%08x\n",
        a6_wifi_caps_attempted, a6_wifi_caps_result, a6_wifi_caps_restore,
        a6_wifi_caps_gate_writes, a6_wifi_caps_before, a6_wifi_caps_after,
        a6_wifi_caps_words[0], a6_wifi_caps_words[1],
        a6_wifi_caps_words[2], a6_wifi_caps_words[3],
        a6_wifi_caps_command, a6_wifi_caps_status);
    mutex_unlock(&a6_wifi_caps_lock);
    return result;
}

static ssize_t a6_wifi_caps_run(struct kobject *kobj,
                               struct kobj_attribute *attr,
                               const char *buf, size_t count)
{
    void __iomem *pmgr = NULL, *usb_ctl = NULL, *ehci = NULL;
    u32 value;
    unsigned int i;
    int ret;

    if (!sysfs_streq(buf, "read-caps-once-n42"))
        return -EINVAL;
    mutex_lock(&a6_wifi_caps_lock);
    if (a6_wifi_caps_attempted) {
        ret = -EALREADY;
        goto out;
    }
    a6_wifi_caps_attempted = true;
    ret = -ENOMEM;
    pmgr = ioremap(0x3f100000, 0x2000);
    usb_ctl = ioremap(0x3f108000, 0x1000);
    ehci = ioremap(0x36400000, 0x1000);
    if (!pmgr || !usb_ctl || !ehci)
        goto finish;
    a6_wifi_caps_before = readl(pmgr + 0x108c);
    /* Exact inherited-state trial; do not change shared dependencies,
     * secondary clocks or USB control to make an unknown state fit.
     */
    ret = -EPROTO;
    if (a6_wifi_caps_before != 0x200 ||
        readl(pmgr + 0x1084) != 0x2ff ||
        readl(pmgr + 0x109c) != 0x2ff ||
        readl(pmgr + 0x2a4) != 0x82000001 ||
        readl(pmgr + 0x2a8) != 0x82000001 ||
        (readl(usb_ctl) & 0x20))
        goto finish;
    /* Stock primary update: preserve outside 0x10f, request f. */
    writel((a6_wifi_caps_before & ~0x10f) | 0xf, pmgr + 0x108c);
    a6_wifi_caps_gate_writes++;
    ret = readl_poll_timeout(pmgr + 0x108c, value,
                            (value & 0xff) == 0xff, 100, 100000);
    if (!ret) {
        a6_wifi_caps_words[0] = readl(ehci);
        /* Validate the operational offset before reading inherited state.
         * Do not continue if enabling the gate exposed a running engine.
         */
        value = a6_wifi_caps_words[0] & 0xff;
        if (value < 0x10 || value > 0x80 || (value & 3) ||
            (a6_wifi_caps_words[0] >> 16) != 0x100) {
            ret = -ENODEV;
        } else {
            a6_wifi_caps_command = readl(ehci + value);
            a6_wifi_caps_status = readl(ehci + value + 4);
            if ((a6_wifi_caps_command & 1) ||
                !(a6_wifi_caps_status & BIT(12))) {
                ret = -EBUSY;
            } else {
                for (i = 1; i < ARRAY_SIZE(a6_wifi_caps_words); i++)
                    a6_wifi_caps_words[i] = readl(ehci + i * 4);
                if ((a6_wifi_caps_words[1] & 0xf) < 4)
                    ret = -ENODEV;
            }
        }
    }
    /* Restore even after enable timeout or invalid capabilities. */
    value = readl(pmgr + 0x108c);
    writel((value & ~0x10f) | (a6_wifi_caps_before & 0xf), pmgr + 0x108c);
    a6_wifi_caps_gate_writes++;
    a6_wifi_caps_restore = readl_poll_timeout(pmgr + 0x108c, value,
                                             !(value & 0xff), 100, 100000);
    a6_wifi_caps_after = readl(pmgr + 0x108c);
    if (!a6_wifi_caps_restore && a6_wifi_caps_after != a6_wifi_caps_before)
        a6_wifi_caps_restore = -EPROTO;
    if (a6_wifi_caps_restore)
        ret = a6_wifi_caps_restore;
finish:
    if (ehci)
        iounmap(ehci);
    if (usb_ctl)
        iounmap(usb_ctl);
    if (pmgr)
        iounmap(pmgr);
    a6_wifi_caps_result = ret;
    pr_info("A6_WIFI_EHCI_CAPS_V1 result=%d restore=%d gate_writes=%u caps=%08x/%08x/%08x/%08x\n",
        ret, a6_wifi_caps_restore, a6_wifi_caps_gate_writes,
        a6_wifi_caps_words[0], a6_wifi_caps_words[1],
        a6_wifi_caps_words[2], a6_wifi_caps_words[3]);
out:
    mutex_unlock(&a6_wifi_caps_lock);
    return ret ? ret : count;
}

static struct kobj_attribute a6_wifi_caps_status_attr =
    __ATTR(status, 0400, a6_wifi_caps_show, NULL);
static struct kobj_attribute a6_wifi_caps_run_attr =
    __ATTR(run, 0200, NULL, a6_wifi_caps_run);
static struct attribute *a6_wifi_caps_attrs[] = {
    &a6_wifi_caps_status_attr.attr, &a6_wifi_caps_run_attr.attr, NULL
};
static const struct attribute_group a6_wifi_caps_group = {
    .name = "a6_wifi_ehci_caps", .attrs = a6_wifi_caps_attrs
};

static int __init a6_wifi_caps_init(void)
{
    if (!of_machine_is_compatible("apple,n42ap"))
        return 0;
    return sysfs_create_group(firmware_kobj, &a6_wifi_caps_group);
}
late_initcall(a6_wifi_caps_init);

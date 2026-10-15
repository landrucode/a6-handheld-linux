extern void a6_ehci_reset_trial(void);
// SPDX-License-Identifier: GPL-2.0-only
/* N42-only, root-requested WLAN enumeration. No firmware or association. */
#include <linux/iopoll.h>
#include <linux/mutex.h>

extern ssize_t a6_ehci_identity(char *buf);
extern ssize_t a6_ehci_otp(char *buf);
extern ssize_t a6_ehci_download(char *buf);
extern ssize_t a6_ehci_execute(char *buf);
extern ssize_t a6_ehci_runtime(char *buf);
extern ssize_t a6_ehci_preflight(char *buf);
extern ssize_t a6_ehci_preflight_data(char *buf, loff_t off, size_t count);
extern ssize_t a6_ehci_bulk_rx(char *buf);
extern ssize_t a6_ehci_loopback(char *buf);
extern ssize_t a6_ehci_bulk_rx_data(char *buf, loff_t off, size_t count);
extern ssize_t a6_ehci_progress(char *buf);
extern int a6_ehci_trial(void __iomem *regs, u32 *words);
#ifdef A6_WIFI_NATIVE
extern int a6_ehci_native_start(void __iomem *regs, u32 *words);
extern void a6_ehci_native_stop(void);
extern bool a6_ehci_native_active(void);
static void __iomem *a6_native_pmgr, *a6_native_control, *a6_native_phy, *a6_native_ehci;
#endif
static DEFINE_MUTEX(a6_wifi_enum_lock);
static bool a6_wifi_enum_attempted;
static int a6_wifi_enum_result = -EAGAIN, a6_wifi_enum_restore = -EAGAIN;
static unsigned int a6_wifi_enum_stage;
static u32 a6_wifi_enum_data[9], a6_wifi_enum_phy[3], a6_wifi_enum_control;
static u8 a6_wifi_enum_reset_before, a6_wifi_enum_reset_after;
static unsigned int a6_wifi_enum_submitted, a6_wifi_enum_completed;
static unsigned int a6_wifi_enum_restore_submitted, a6_wifi_enum_restore_completed;
static unsigned int a6_wifi_enum_mmio_writes;
static u32 a6_wifi_enum_gate_before, a6_wifi_enum_gate_after;
static u32 a6_wifi_enum_phy_after, a6_wifi_enum_control_after;
static int a6_wifi_enum_reset_readback = -EAGAIN;

/* Serialize individual PMU operations with charging/touch, without holding
 * their lock across the reset waits or the EHCI observation window. */
static int a6_wifi_reset_read(u8 *value)
{
    int ret;
    mutex_lock(&a6_touch_lock);
    ret = a6_power_validate();
    if (!ret) ret = a6_policy_reg(0x72, value, false);
    mutex_unlock(&a6_touch_lock);
    return ret;
}
static int a6_wifi_reset_write(u8 value, unsigned int *submitted)
{
    int ret;
    mutex_lock(&a6_touch_lock);
    ret = a6_power_validate();
    if (!ret) ret = a6_power_combo_reset(a6_wifi_enum_reset_before,
                                        value, submitted);
    mutex_unlock(&a6_touch_lock);
    return ret;
}

static ssize_t a6_wifi_enum_show(struct kobject *kobj,
                               struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = sysfs_emit(buf,
        "A6_WIFI_EHCI_ENUM_V2 attempted=%u result=%d restore=%d stage=%u "
        "vid=%04x pid=%04x speed=%u state=%u irq_calls=%u port4=%08x "
        "phy0=%08x phy4=%08x phy8=%08x usb_ctl=%08x reset72=%02x "
        "pmu_submitted=%u pmu_completed=%u pmu_restore_submitted=%u "
        "pmu_restore_completed=%u mmio_writes=%u reset_readback=%d "
        "reset72_after=%02x gate_before=%08x gate_after=%08x "
        "phy8_after=%08x usb_ctl_after=%08x irq_fault=%u irq_status=%08x irq_restarts=%u\n",
        a6_wifi_enum_attempted, a6_wifi_enum_result, a6_wifi_enum_restore,
        a6_wifi_enum_stage, a6_wifi_enum_data[0], a6_wifi_enum_data[1],
        a6_wifi_enum_data[2], a6_wifi_enum_data[3], a6_wifi_enum_data[4],
        a6_wifi_enum_data[5], a6_wifi_enum_phy[0], a6_wifi_enum_phy[1],
        a6_wifi_enum_phy[2], a6_wifi_enum_control, a6_wifi_enum_reset_before,
        a6_wifi_enum_submitted, a6_wifi_enum_completed,
        a6_wifi_enum_restore_submitted, a6_wifi_enum_restore_completed,
        a6_wifi_enum_mmio_writes, a6_wifi_enum_reset_readback,
        a6_wifi_enum_reset_after, a6_wifi_enum_gate_before, a6_wifi_enum_gate_after,
        a6_wifi_enum_phy_after, a6_wifi_enum_control_after,
        a6_wifi_enum_data[6], a6_wifi_enum_data[7], a6_wifi_enum_data[8]);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}

static ssize_t a6_wifi_enum_run(struct kobject *kobj,
                              struct kobj_attribute *attr,
                              const char *buf, size_t count)
{
    void __iomem *pmgr = NULL, *control = NULL, *phy = NULL, *ehci = NULL;
    bool gate_owned = false, phy_owned = false, reset_owned = false;
    u32 value, gate_before = 0;
    u8 reset;
    unsigned int i;
    int ret = -ENOMEM, restore = 0, cr;
#ifdef A6_WIFI_NATIVE
    bool native = sysfs_streq(buf, "start-native-n42-wlan");
    bool stop = sysfs_streq(buf, "stop-native-n42-wlan");
#endif

    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    if (!sysfs_streq(buf, "enumerate-once-n42-wlan")
#ifdef A6_WIFI_NATIVE
        && !native && !stop
#endif
       ) return -EINVAL;
    mutex_lock(&a6_wifi_enum_lock);
#ifdef A6_WIFI_NATIVE
    if (a6_ehci_native_active()) {
        if (!stop) {
            mutex_unlock(&a6_wifi_enum_lock);
            return native ? count : -EBUSY;
        }
        /* Restore only after native URBs/driver and HCD have disconnected. */
        a6_ehci_native_stop();
        pmgr = a6_native_pmgr; control = a6_native_control;
        phy = a6_native_phy; ehci = a6_native_ehci;
        a6_native_pmgr = a6_native_control = a6_native_phy = a6_native_ehci = NULL;
        gate_owned = phy_owned = reset_owned = true;
        gate_before = a6_wifi_enum_gate_before;
        ret = 0;
        goto finish;
    }
    if (stop) { mutex_unlock(&a6_wifi_enum_lock); return count; }
#endif
    a6_wifi_enum_attempted = true;
    a6_wifi_enum_stage = a6_wifi_enum_submitted = a6_wifi_enum_completed = 0;
    a6_wifi_enum_restore_submitted = a6_wifi_enum_restore_completed = a6_wifi_enum_mmio_writes = 0;
    memset(a6_wifi_enum_data, 0, sizeof(a6_wifi_enum_data));
    /* Require the proven protection to be running, without changing it. */
    ret = -EPERM;
    if (!a6_auto_enabled || a6_auto_fault || a6_auto_paused ||
        !a6_low_enabled || a6_low_triggered || a6_low_attended_trial ||
        a6_low_attended_plugged)
        goto finish;
    ret = -ENOMEM;
    pmgr = ioremap(0x3f100000, 0x2000);
    control = ioremap(0x3f108000, 0x1000);
    phy = ioremap(0x36000000, 0x1000);
    ehci = ioremap(0x36400000, 0x1000);
    if (!pmgr || !control || !phy || !ehci)
        goto finish;
    gate_before = readl(pmgr + 0x108c);
    a6_wifi_enum_gate_before = gate_before;
    a6_wifi_enum_control = readl(control);
    ret = -EPROTO;
    if (gate_before != 0x200 || readl(pmgr + 0x1084) != 0x2ff ||
        readl(pmgr + 0x109c) != 0x2ff ||
        readl(pmgr + 0x2a4) != 0x82000001 ||
        readl(pmgr + 0x2a8) != 0x82000001 ||
        (a6_wifi_enum_control & 0x20))
        goto finish;
    for (i = 0; i < 3; i++)
        a6_wifi_enum_phy[i] = readl(phy + i * 4);
    /* Global PHY must already be awake. Never reset/tune the gadget PHY. */
    if ((a6_wifi_enum_phy[0] & 1) || (a6_wifi_enum_phy[2] & 3))
        goto finish;
    ret = a6_wifi_reset_read(&a6_wifi_enum_reset_before);
    if (ret)
        goto finish;
    ret = -EPROTO;
    if (a6_wifi_enum_reset_before & ~0x1f)
        goto finish;
    a6_wifi_enum_stage = 1;
    gate_owned = true;
    a6_wifi_enum_mmio_writes++;
    writel((gate_before & ~0x10f) | 0xf, pmgr + 0x108c);
    ret = readl_poll_timeout(pmgr + 0x108c, value,
                            (value & 0xff) == 0xff, 100, 100000);
    if (ret)
        goto finish;
    ret = -EBUSY;
    if (readl(ehci) != 0x01000010 || (readl(ehci + 0x10) & 1) ||
        !(readl(ehci + 0x14) & BIT(12)))
        goto finish;
    /* Other clients must be disconnected/disabled before global HC reset.
     * The standard driver filters every PORTSC1..3 read/write thereafter.
     */
    for (i = 0; i < 3; i++)
        if (readl(ehci + 0x54 + i * 4) & (BIT(0) | BIT(2)))
            goto finish;
    a6_wifi_enum_stage = 2;
    phy_owned = true;
    /* Stock selector 4: clear only its power-down bit, preserving others.
     * Stock _configureHSIC leaves usb_ctl bit 2 set for an active client.
     */
    a6_wifi_enum_mmio_writes++;
    writel(readl(phy + 8) & ~0x20, phy + 8);
    a6_wifi_enum_mmio_writes++;
    writel(readl(control) | BIT(2), control);
    msleep(20);
    ret = -EIO;
    if ((readl(phy + 8) & 0x20) || !(readl(control) & BIT(2)))
        goto finish;
    /* Stock PMU GPIO10 reset pulse: logical 1 then 0, inverted bit 1.
     * This resets the WLAN/Bluetooth combo module, not the baseband.
     */
    reset = a6_wifi_enum_reset_before & 0x1d;
    ret = a6_wifi_reset_write(reset,
                              &a6_wifi_enum_submitted);
    reset_owned = a6_wifi_enum_submitted != 0;
    if (!ret) a6_wifi_enum_completed++;
    if (ret)
        goto finish;
    msleep(500);
    reset |= 2;
    ret = a6_wifi_reset_write(reset,
                              &a6_wifi_enum_submitted);
    reset_owned = a6_wifi_enum_submitted != 0;
    if (!ret) a6_wifi_enum_completed++;
    if (ret)
        goto finish;
    msleep(100);
    a6_wifi_enum_stage = 3;
    a6_ehci_reset_trial();
#ifdef A6_WIFI_NATIVE
    ret = native ? a6_ehci_native_start(ehci, a6_wifi_enum_data) :
                   a6_ehci_trial(ehci, a6_wifi_enum_data);
#else
    ret = a6_ehci_trial(ehci, a6_wifi_enum_data);
#endif
    a6_wifi_enum_stage = 4;
#ifdef A6_WIFI_NATIVE
    if (!ret && native && a6_ehci_native_active()) {
        a6_native_pmgr = pmgr; a6_native_control = control;
        a6_native_phy = phy; a6_native_ehci = ehci;
        a6_wifi_enum_result = 0;
        a6_wifi_enum_restore = -EINPROGRESS;
        pr_info("A6_WIFI_NATIVE_V1 active=1 runtime_ready=1\n");
        mutex_unlock(&a6_wifi_enum_lock);
        return count;
    }
#endif
finish:
    if (reset_owned) {
        cr = a6_wifi_reset_write(a6_wifi_enum_reset_before,
                                 &a6_wifi_enum_restore_submitted);
        if (!cr) a6_wifi_enum_restore_completed++;
        if (cr) restore = cr;
    }
    if (a6_wifi_enum_stage >= 1) {
        a6_wifi_enum_reset_readback = a6_wifi_reset_read(&a6_wifi_enum_reset_after);
        if (a6_wifi_enum_reset_readback) restore = a6_wifi_enum_reset_readback;
        else if (a6_wifi_enum_reset_after != a6_wifi_enum_reset_before)
            restore = -EIO;
    }
    if (phy_owned) {
        value = (readl(phy + 8) & ~0x20) | (a6_wifi_enum_phy[2] & 0x20);
        a6_wifi_enum_mmio_writes++;
        writel(value, phy + 8);
        value = (readl(control) & ~BIT(2)) | (a6_wifi_enum_control & BIT(2));
        a6_wifi_enum_mmio_writes++;
        writel(value, control);
        if ((readl(phy + 8) & 0x20) != (a6_wifi_enum_phy[2] & 0x20) ||
            (readl(control) & BIT(2)) != (a6_wifi_enum_control & BIT(2)))
            restore = -EIO;
    }
    if (gate_owned) {
        value = readl(pmgr + 0x108c);
        a6_wifi_enum_mmio_writes++;
        writel((value & ~0x10f) | (gate_before & 0xf), pmgr + 0x108c);
        cr = readl_poll_timeout(pmgr + 0x108c, value,
                                !(value & 0xff), 100, 100000);
        if (!cr && value != gate_before) cr = -EIO;
        if (cr) restore = cr;
    }
    if (a6_wifi_enum_stage >= 1) {
        a6_wifi_enum_gate_after = readl(pmgr + 0x108c);
        a6_wifi_enum_phy_after = readl(phy + 8);
        a6_wifi_enum_control_after = readl(control);
    }
    if (ehci) iounmap(ehci);
    if (phy) iounmap(phy);
    if (control) iounmap(control);
    if (pmgr) iounmap(pmgr);
    a6_wifi_enum_result = ret;
    a6_wifi_enum_restore = restore;
    pr_info("A6_WIFI_EHCI_ENUM_V2 result=%d restore=%d stage=%u vid=%04x pid=%04x\n",
            ret, restore, a6_wifi_enum_stage, a6_wifi_enum_data[0], a6_wifi_enum_data[1]);
    mutex_unlock(&a6_wifi_enum_lock);
    return ret ? ret : count;
}

#ifdef A6_WIFI_NATIVE
static ssize_t a6_wifi_native_show(struct kobject *kobj,
                                  struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = sysfs_emit(buf, "A6_WIFI_NATIVE_V1 active=%u result=%d restore=%d\n",
                   a6_ehci_native_active(), a6_wifi_enum_result, a6_wifi_enum_restore);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_native = __ATTR(native, 0400, a6_wifi_native_show, NULL);
#endif
static ssize_t a6_wifi_progress_show(struct kobject *kobj,
                                    struct kobj_attribute *attr, char *buf)
{
    return a6_ehci_progress(buf);
}
static struct kobj_attribute a6_wifi_enum_progress = __ATTR(progress, 0400, a6_wifi_progress_show, NULL);
static ssize_t a6_wifi_identity_show(struct kobject *kobj,
                                    struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    /* Read after the one-shot writer completes, just like final status. */
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_identity(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_identity = __ATTR(identity, 0400, a6_wifi_identity_show, NULL);
static ssize_t a6_wifi_otp_show(struct kobject *kobj,
                               struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_otp(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_otp = __ATTR(otp, 0400, a6_wifi_otp_show, NULL);
static ssize_t a6_wifi_download_show(struct kobject *kobj,
                                    struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_download(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_download = __ATTR(download, 0400, a6_wifi_download_show, NULL);
static ssize_t a6_wifi_execute_show(struct kobject *kobj,
                                   struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_execute(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_execute = __ATTR(execute, 0400, a6_wifi_execute_show, NULL);
static ssize_t a6_wifi_runtime_show(struct kobject *kobj,
                                   struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_runtime(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_runtime = __ATTR(runtime, 0400, a6_wifi_runtime_show, NULL);
static ssize_t a6_wifi_bulk_rx_show(struct kobject *kobj,
                                  struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_bulk_rx(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static ssize_t a6_wifi_loopback_show(struct kobject *kobj,
                                   struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_loopback(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_loopback = __ATTR(loopback, 0400, a6_wifi_loopback_show, NULL);
static struct kobj_attribute a6_wifi_enum_bulk_rx = __ATTR(bulk_rx, 0400, a6_wifi_bulk_rx_show, NULL);
static ssize_t a6_wifi_bulk_rx_data_read(struct file *file, struct kobject *kobj,
        const struct bin_attribute *attr, char *buf, loff_t off, size_t count)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_bulk_rx_data(buf, off, count);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static const struct bin_attribute a6_wifi_enum_bulk_rx_data = {
    .attr = { .name = "bulk_rx_data", .mode = 0400 },
    .size = 32864, /* bounded sixteen-packet journal on loopback builds */
    .read = a6_wifi_bulk_rx_data_read,
};
static ssize_t a6_wifi_preflight_show(struct kobject *kobj,
        struct kobj_attribute *attr, char *buf)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_preflight(buf);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static struct kobj_attribute a6_wifi_enum_preflight = __ATTR(preflight, 0400, a6_wifi_preflight_show, NULL);
static ssize_t a6_wifi_preflight_data_read(struct file *file, struct kobject *kobj,
        const struct bin_attribute *attr, char *buf, loff_t off, size_t count)
{
    ssize_t n;
    mutex_lock(&a6_wifi_enum_lock);
    n = a6_ehci_preflight_data(buf, off, count);
    mutex_unlock(&a6_wifi_enum_lock);
    return n;
}
static const struct bin_attribute a6_wifi_enum_preflight_data = {
    .attr = { .name = "preflight_data", .mode = 0400 },
    .size = 136000, .read = a6_wifi_preflight_data_read,
};
static struct kobj_attribute a6_wifi_enum_status = __ATTR(status, 0400, a6_wifi_enum_show, NULL);
static struct kobj_attribute a6_wifi_enum_once = __ATTR(run, 0200, NULL, a6_wifi_enum_run);
static int __init a6_wifi_enum_init(void)
{
    struct kobject *kobj;
    int ret;
    kobj = kobject_create_and_add("a6_wifi_ehci_enum", firmware_kobj);
    if (!kobj) return -ENOMEM;
    ret = sysfs_create_file(kobj, &a6_wifi_enum_status.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_identity.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_otp.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_download.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_execute.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_runtime.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_preflight.attr);
    if (!ret) ret = sysfs_create_bin_file(kobj, &a6_wifi_enum_preflight_data);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_bulk_rx.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_loopback.attr);
    if (!ret) ret = sysfs_create_bin_file(kobj, &a6_wifi_enum_bulk_rx_data);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_progress.attr);
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_once.attr);
#ifdef A6_WIFI_NATIVE
    if (!ret) ret = sysfs_create_file(kobj, &a6_wifi_enum_native.attr);
#endif
    if (ret) kobject_put(kobj);
    return ret;
}
late_initcall(a6_wifi_enum_init);

// SPDX-License-Identifier: GPL-2.0-only
/* Bounded N42 WLAN enumeration using Linux's normal EHCI and DMA APIs.
 * Called explicitly by the framebuffer diagnostic; never probes at boot.
 */
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/crc32.h>
#include <linux/unaligned.h>
#include <linux/dma-map-ops.h>
#include <linux/dma-mapping.h>
#include <linux/irqdomain.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/slab.h>
#include <linux/usb.h>
#include <linux/sysfs.h>
#include <linux/usb/hcd.h>
#include "ehci.h"

int a6_ehci_trial(void __iomem *regs, u32 *words);
ssize_t a6_ehci_progress(char *buf);
static atomic_t a6_trial_irqs = ATOMIC_INIT(0);
static atomic_t a6_irq_handled = ATOMIC_INIT(0), a6_irq_none = ATOMIC_INIT(0);
static u32 a6_irq_none_streak, a6_irq_raw_status, a6_irq_enable;
static unsigned long a6_irq_enter_jiffies, a6_irq_exit_jiffies;
static u32 a6_trial_phase, a6_trial_elapsed;
#ifdef A6_WIFI_NATIVE
static struct usb_hcd *a6_native_hcd;
static struct platform_device *a6_native_pdev;
static bool a6_native_requested;
static const struct property_entry a6_native_properties[] = {
    PROPERTY_ENTRY_BOOL("apple,a6-runtime-ready"),
    PROPERTY_ENTRY_BOOL("apple,hsic-usb-header"),
    { }
};
int a6_ehci_native_start(void __iomem *regs, u32 *words);
void a6_ehci_native_stop(void);
bool a6_ehci_native_active(void);

#endif
/* A separate lockless endpoint remains readable during a blocked HCD call. */
ssize_t a6_ehci_progress(char *buf)
{
    return sysfs_emit(buf, "A6_EHCI_PROGRESS_V1 phase=%u elapsed=%u irq_calls=%d "
                      "handled=%d none=%d none_streak=%u raw_status=%08x intr_enable=%08x "
                      "enter_jiffies=%lu exit_jiffies=%lu\n",
                      READ_ONCE(a6_trial_phase), READ_ONCE(a6_trial_elapsed),
                      atomic_read(&a6_trial_irqs), atomic_read(&a6_irq_handled),
                      atomic_read(&a6_irq_none), READ_ONCE(a6_irq_none_streak),
                      READ_ONCE(a6_irq_raw_status), READ_ONCE(a6_irq_enable),
                      READ_ONCE(a6_irq_enter_jiffies), READ_ONCE(a6_irq_exit_jiffies));
}

ssize_t a6_ehci_identity(char *buf);
static int a6_identity_result = -EAGAIN, a6_identity_length = -1;
static u32 a6_identity_words[6];
static unsigned int a6_identity_submitted, a6_identity_fields;
ssize_t a6_ehci_identity(char *buf)
{
#ifdef A6_WIFI_USB_IDENTITY
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    return sysfs_emit(buf,
        "A6_WIFI_USB_IDENTITY_V1 enabled=%u result=%d length=%d submitted=%u "
        "fields=%02x request=05 type=c1 value=0001 index=0000 "
        "chip=%08x chiprev=%08x ramsize=%08x remapbase=%08x boardtype=%08x boardrev=%08x\n",
        enabled, READ_ONCE(a6_identity_result), READ_ONCE(a6_identity_length),
        READ_ONCE(a6_identity_submitted), READ_ONCE(a6_identity_fields),
        a6_identity_words[0], a6_identity_words[1], a6_identity_words[2],
        a6_identity_words[3], a6_identity_words[4], a6_identity_words[5]);
}
#ifdef A6_WIFI_USB_IDENTITY
/* Linux brcmfmac DL_GETVER wire layout; Cascadia's BCM4334 HSIC wValue=1.
 * Only a vendor IN request to the observed N42 port4 identity; no firmware,
 * DL_START/GO/RESETCFG, bulk OUT, host-ready transition or association.
 */
static void a6_trial_get_identity(struct usb_device *udev)
{
    __le32 *reply;
    unsigned int i;
    int ret = -EPROTO;

    if (!usb_trylock_device(udev)) {
        WRITE_ONCE(a6_identity_result, -EBUSY);
        return;
    }
    if (udev->state != USB_STATE_CONFIGURED ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a ||
        !udev->actconfig || !udev->actconfig->desc.bNumInterfaces ||
        !udev->actconfig->interface[0] ||
        !udev->actconfig->interface[0]->cur_altsetting ||
        udev->actconfig->interface[0]->cur_altsetting->desc.bInterfaceNumber != 0)
        goto unlock;
    reply = kzalloc(6 * sizeof(*reply), GFP_KERNEL); /* DMA-safe transfer buffer */
    if (!reply) {
        ret = -ENOMEM;
        goto unlock;
    }
    WRITE_ONCE(a6_trial_phase, 9);
    pr_info("A6_WIFI_USB_IDENTITY_V1 getver_begin value=1 bytes=24\n");
    a6_identity_submitted++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 5,
                          USB_DIR_IN | USB_TYPE_VENDOR | USB_RECIP_INTERFACE,
                          1, 0, reply, 6 * sizeof(*reply), 2000);
    WRITE_ONCE(a6_identity_length, ret);
    /* Some ROMs expose only chip/revision. Missing fields are never inferred. */
    if (ret >= 8 && ret <= 24 && !(ret & 3)) {
        for (i = 0; i < ret / sizeof(*reply); i++) {
            a6_identity_words[i] = le32_to_cpu(reply[i]);
            a6_identity_fields |= BIT(i);
        }
        ret = 0;
    } else if (ret >= 0) {
        ret = -EMSGSIZE;
    }
    kfree(reply);
unlock:
    WRITE_ONCE(a6_identity_result, ret);
    pr_info("A6_WIFI_USB_IDENTITY_V1 getver_end result=%d length=%d fields=%02x\n",
            ret, a6_identity_length, a6_identity_fields);
    usb_unlock_device(udev);
}
#endif

ssize_t a6_ehci_otp(char *buf);
static int a6_otp_result = -EAGAIN;
static unsigned int a6_otp_submitted, a6_otp_completed, a6_otp_bytes;
static u32 a6_otp_start, a6_otp_end;
static u8 a6_otp_data[512];
ssize_t a6_ehci_otp(char *buf)
{
#ifdef A6_WIFI_USB_OTP
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    ssize_t n;
    unsigned int i;
    n = sysfs_emit(buf, "A6_WIFI_USB_OTP_V1 enabled=%u result=%d submitted=%u completed=%u "
                   "bytes=%u start=%u end=%u request=11 type=c1 reply_bytes=16 data_word=3 data=",
                   enabled, a6_otp_result, a6_otp_submitted, a6_otp_completed,
                   a6_otp_bytes, a6_otp_start, a6_otp_end);
    /* Private calibration/identity bytes: root-readable endpoint only. */
    for (i = 0; i < a6_otp_bytes; i++)
        n += sysfs_emit_at(buf, n, "%02x", a6_otp_data[i]);
    return n + sysfs_emit_at(buf, n, "\n");
}
#ifdef A6_WIFI_USB_OTP
/* Pinned stock BCM4334 chip-manager dispatch, verified offline by
 * verify-a6-wifi-otp-read.py. IN reads only; no OTP programming/download.
 * Refuse invalid/oversized ranges instead of stock's fallback to 512 bytes.
 */
static int a6_trial_otp_word(struct usb_device *udev, __le32 *reply,
                             u32 address, unsigned long deadline, u32 *value)
{
    int ret;
    unsigned int timeout;
    if (time_after_eq(jiffies, deadline))
        return -ETIMEDOUT;
    timeout = min_t(unsigned int, 250, jiffies_to_msecs(deadline - jiffies));
    if (!timeout)
        return -ETIMEDOUT;
    memset(reply, 0, 16);
    a6_otp_submitted++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 0x11,
                          USB_DIR_IN | USB_TYPE_VENDOR | USB_RECIP_INTERFACE,
                          address & 0xffff, address >> 16, reply, 16, timeout);
    if (ret != 16)
        return ret < 0 ? ret : -EMSGSIZE;
    a6_otp_completed++;
    *value = le32_to_cpu(reply[3]);
    return 0;
}
static void a6_trial_get_otp(struct usb_device *udev)
{
    __le32 *reply;
    unsigned long deadline;
    u32 start_word, end_word, value, length, offset;
    int ret = -EPROTO;
    /* Require the exact full identity measured in the accepted trial. */
    if (a6_identity_result || a6_identity_fields != 0x3f ||
        a6_identity_words[0] != 0x4334 || a6_identity_words[1] != 3 ||
        a6_identity_words[2] != 0x80000 || a6_identity_words[3] != 0x60000000)
        goto result;
    if (!usb_trylock_device(udev)) {
        ret = -EBUSY;
        goto result;
    }
    if (udev->state != USB_STATE_CONFIGURED ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a ||
        !udev->actconfig || !udev->actconfig->desc.bNumInterfaces ||
        !udev->actconfig->interface[0] ||
        !udev->actconfig->interface[0]->cur_altsetting ||
        udev->actconfig->interface[0]->cur_altsetting->desc.bInterfaceNumber != 0)
        goto unlock;
    reply = kzalloc(16, GFP_KERNEL);
    if (!reply) {
        ret = -ENOMEM;
        goto unlock;
    }
    WRITE_ONCE(a6_trial_phase, 10);
    deadline = jiffies + msecs_to_jiffies(10000);
    ret = a6_trial_otp_word(udev, reply, 0x1800083a, deadline, &end_word);
    if (ret)
        goto free;
    ret = a6_trial_otp_word(udev, reply, 0x18000838, deadline, &start_word);
    if (ret)
        goto free;
    a6_otp_start = (start_word >> 3) & 0x1fff;
    a6_otp_end = (end_word >> 3) & 0x1fff;
    if (a6_otp_end <= a6_otp_start ||
        (a6_otp_start | a6_otp_end) & 1 ||
        a6_otp_end - a6_otp_start > sizeof(a6_otp_data)) {
        ret = -ERANGE;
        goto free;
    }
    length = a6_otp_end - a6_otp_start;
    for (offset = 0; offset < length; offset += 2) {
        ret = a6_trial_otp_word(udev, reply, 0x18000800 + a6_otp_start + offset,
                              deadline, &value);
        if (ret)
            goto free;
        a6_otp_data[offset] = value & 0xff;
        a6_otp_data[offset + 1] = (value >> 8) & 0xff;
        a6_otp_bytes += 2;
    }
free:
    kfree(reply);
unlock:
    usb_unlock_device(udev);
result:
    /* Export no partial calibration on failed reads. */
    if (ret) {
        memset(a6_otp_data, 0, sizeof(a6_otp_data));
        a6_otp_bytes = 0;
    }
    a6_otp_result = ret;
    pr_info("A6_WIFI_USB_OTP_V1 result=%d submitted=%u completed=%u bytes=%u\n",
            ret, a6_otp_submitted, a6_otp_completed, a6_otp_bytes);
}
#endif

#include "a6-wifi-usb-download.inc"
#include "a6-wifi-usb-runtime.inc"
#include "a6-wifi-usb-preflight.inc"
#include "a6-wifi-usb-bulk-rx.inc"
#include "a6-wifi-usb-loopback.inc"
#ifdef A6_WIFI_USB_SCAN
#include "a6-wifi-usb-scan.inc"
#endif

static struct hc_driver a6_trial_driver;
static irqreturn_t (*a6_trial_irq)(struct usb_hcd *);

static irqreturn_t a6_trial_interrupt(struct usb_hcd *hcd)
{
    struct ehci_hcd *ehci = hcd_to_ehci(hcd);
    irqreturn_t result;
    atomic_inc(&a6_trial_irqs);
    WRITE_ONCE(a6_irq_enter_jiffies, jiffies);
    WRITE_ONCE(a6_irq_raw_status, ehci_readl(ehci, &ehci->regs->status));
    WRITE_ONCE(a6_irq_enable, ehci_readl(ehci, &ehci->regs->intr_enable));
    result = a6_trial_irq(hcd);
    WRITE_ONCE(a6_irq_exit_jiffies, jiffies);
    if (result == IRQ_NONE) {
        atomic_inc(&a6_irq_none);
        /* A dedicated HSIC line repeatedly unclaimed by EHCI cannot carry
         * valid completions. Stop its outer AIC re-entry storm, preserving
         * USB recovery and the independent battery IRQs. No reset/retry. */
        if (++a6_irq_none_streak >= 256 && !ehci->a6_irq_fault) {
            WRITE_ONCE(ehci->a6_irq_fault, true);
            disable_irq_nosync(hcd->irq);
            pr_err("A6_HSIC_IRQ_UNCLAIMED_V1 masked irq=%u status=%08x enable=%08x streak=%u\n",
                   hcd->irq, a6_irq_raw_status, a6_irq_enable, a6_irq_none_streak);
        }
    } else {
        atomic_inc(&a6_irq_handled);
        WRITE_ONCE(a6_irq_none_streak, 0);
    }
    return result;
}

static int a6_trial_reset(struct usb_hcd *hcd)
{
    struct ehci_hcd *ehci = hcd_to_ehci(hcd);
    /* This flag filters PORTSC1..3 at the common read/write boundary,
     * including start, IRQ, root-hub operations and teardown.
     */
    ehci->a6_wlan_only = true;
    ehci->caps = hcd->regs;
    return ehci_setup(hcd);
}

/* USB core uses controller->driver (or sysdev->driver) during enumeration.
 * Register a real synchronous platform binding before creating the HCD.
 * Registration happens only inside the explicit one-shot, not at boot.
 */
static int a6_trial_platform_probe(struct platform_device *pdev)
{
    return 0;
}
static struct platform_driver a6_trial_platform_driver = {
    .probe = a6_trial_platform_probe,
    .driver = {
        .name = "a6-wlan-ehci-trial",
        .probe_type = PROBE_FORCE_SYNCHRONOUS,
    },
};

struct a6_trial_capture {
    struct usb_bus *bus;
    u32 *words;
#ifdef A6_WIFI_USB_IDENTITY
    struct usb_device *device;
#endif
};

static int a6_trial_device(struct usb_device *udev, void *context)
{
    struct a6_trial_capture *capture = context;
    if (udev->bus == capture->bus && udev->parent == udev->bus->root_hub &&
        udev->portnum == 4 && udev->state >= USB_STATE_ADDRESS) {
        capture->words[0] = le16_to_cpu(udev->descriptor.idVendor);
        capture->words[1] = le16_to_cpu(udev->descriptor.idProduct);
        capture->words[2] = udev->speed;
        capture->words[3] = udev->state;
#ifdef A6_WIFI_USB_IDENTITY
        if (udev->state == USB_STATE_CONFIGURED && !capture->device)
            capture->device = usb_get_dev(udev);
#endif
    }
    return 0;
}

void a6_ehci_reset_trial(void);
void a6_ehci_reset_trial(void)
{
    a6_identity_result = a6_otp_result = a6_download_result = a6_execute_result = a6_runtime_result = -EAGAIN;
    a6_identity_submitted = a6_identity_fields = a6_otp_submitted = a6_otp_completed = a6_otp_bytes = 0;
    a6_download_submitted = a6_download_completed = a6_download_control_submitted = a6_download_control_completed = 0;
    a6_download_sent = a6_download_expected = a6_download_rom_bytes = a6_download_endpoint = 0;
    a6_download_state = ~0U;
    a6_execute_go = a6_execute_go_completed = a6_execute_getver = a6_execute_writes = 0;
    a6_execute_reset = a6_execute_restore = -EAGAIN;
    a6_runtime_tx = a6_runtime_rx = a6_runtime_completed = a6_runtime_version_bytes = a6_runtime_inactive_resumes = 0;
    atomic_set(&a6_trial_irqs, 0);
    atomic_set(&a6_irq_handled, 0);
    atomic_set(&a6_irq_none, 0);
    a6_irq_none_streak = a6_irq_raw_status = a6_irq_enable = 0;
    a6_irq_enter_jiffies = a6_irq_exit_jiffies = 0;
    a6_trial_phase = a6_trial_elapsed = 0;
}

#ifdef A6_WIFI_NATIVE
bool a6_ehci_native_active(void) { return !!a6_native_hcd; }
void a6_ehci_native_stop(void)
{
    if (!a6_native_hcd) return;
    /* USB core disconnects brcmfmac and kills its URBs before MMIO teardown. */
    usb_remove_hcd(a6_native_hcd);
    a6_trial_execute_restore();
    usb_put_hcd(a6_native_hcd);
    arch_teardown_dma_ops(&a6_native_pdev->dev);
    platform_device_unregister(a6_native_pdev);
    platform_driver_unregister(&a6_trial_platform_driver);
    a6_native_hcd = NULL;
    a6_native_pdev = NULL;
    WRITE_ONCE(a6_trial_phase, 8);
}
int a6_ehci_native_start(void __iomem *regs, u32 *words)
{
    int ret;
    if (a6_native_hcd) return -EBUSY;
    a6_native_requested = true;
    ret = a6_ehci_trial(regs, words);
    a6_native_requested = false;
    return ret;
}
#endif

int a6_ehci_trial(void __iomem *regs, u32 *words)
{
    const struct ehci_driver_overrides overrides = { .reset = a6_trial_reset };
    struct device_node *node;
    struct irq_domain *domain;
    struct usb_hcd *hcd;
    struct device *dev;
    struct platform_device *pdev;
    struct a6_trial_capture capture;
    unsigned int irq, i;
    int ret;

    WRITE_ONCE(a6_trial_phase, 1);
    pr_info("A6_EHCI_PROGRESS_V1 enter\n");
    node = of_find_compatible_node(NULL, NULL, "apple,s5l8950-aic");
    domain = node ? irq_find_host(node) : NULL;
    of_node_put(node);
    if (!domain)
        return -ENODEV;
    irq = irq_create_mapping(domain, 0x0c);
    if (!irq)
        return -ENXIO;
    ret = platform_driver_register(&a6_trial_platform_driver);
    if (ret)
        return ret;
    pdev = platform_device_register_simple("a6-wlan-ehci-trial", -1, NULL, 0);
    if (IS_ERR(pdev)) {
        ret = PTR_ERR(pdev);
        goto unregister_driver;
    }
    dev = &pdev->dev;
    if (dev->driver != &a6_trial_platform_driver.driver) {
        ret = -ENODEV;
        goto unregister_device;
    }
    pr_info("A6_EHCI_PLATFORM_BOUND_V1 driver=%s\n", dev->driver->name);
    arch_setup_dma_ops(dev, false); /* ARM noncoherent DMA; no snooping assumption. */
    ret = dma_coerce_mask_and_coherent(dev, DMA_BIT_MASK(32));
    if (ret)
        goto unregister;
    ehci_init_driver(&a6_trial_driver, &overrides);
    a6_trial_irq = a6_trial_driver.irq;
    a6_trial_driver.irq = a6_trial_interrupt;
    hcd = usb_create_hcd(&a6_trial_driver, dev, dev_name(dev));
    if (!hcd) {
        ret = -ENOMEM;
        goto unregister;
    }
    hcd->regs = regs;
    hcd->rsrc_start = 0x36400000;
    hcd->rsrc_len = 0x1000;
    WRITE_ONCE(a6_trial_phase, 2);
    pr_info("A6_EHCI_PROGRESS_V1 add_begin\n");
    ret = usb_add_hcd(hcd, irq, 0);
    WRITE_ONCE(a6_trial_phase, 3);
    pr_info("A6_EHCI_PROGRESS_V1 add_end result=%d\n", ret);
    if (!ret) {
        capture.bus = &hcd->self;
        capture.words = words;
#ifdef A6_WIFI_USB_IDENTITY
        capture.device = NULL;
#endif
        /* Twenty-second observation window; USB-core teardown may add time. */
        for (i = 0; i < 20; i++) {
            WRITE_ONCE(a6_trial_phase, 4);
            msleep(1000);
            WRITE_ONCE(a6_trial_elapsed, i + 1);
            if (READ_ONCE(hcd_to_ehci(hcd)->a6_irq_fault))
                break;
            WRITE_ONCE(a6_trial_phase, 5);
            usb_for_each_dev(&capture, a6_trial_device);
#ifdef A6_WIFI_USB_IDENTITY
            if (capture.device)
#else
            if (words[0])
#endif
                break;
        }
#ifdef A6_WIFI_USB_IDENTITY
        if (capture.device) {
            a6_trial_get_identity(capture.device);
#ifdef A6_WIFI_USB_OTP
            a6_trial_get_otp(capture.device);
#ifdef A6_WIFI_USB_DOWNLOAD
            a6_trial_download(capture.device);
#ifdef A6_WIFI_USB_EXECUTE
            a6_trial_execute(capture.device);
#endif
#endif
#endif
            usb_put_dev(capture.device);
#ifdef A6_WIFI_USB_EXECUTE
            capture.device = NULL;
            if (a6_execute_go_completed && a6_execute_result == -EAGAIN) {
                /* One runtime query, after at most ten one-second discovery
                 * observations. No command retries or reset loop. */
                for (i = 0; i < 10; i++) {
                    msleep(1000);
                    if (READ_ONCE(hcd_to_ehci(hcd)->a6_irq_fault))
                        break;
                    usb_for_each_dev(&capture, a6_trial_device);
                    if (capture.device)
                        break;
                }
                if (capture.device) {
                    a6_trial_runtime_identity(capture.device);
#ifdef A6_WIFI_USB_RUNTIME
                    if (!a6_execute_result)
                        a6_trial_runtime_probe(capture.device);
#ifdef A6_WIFI_NATIVE
                    if (a6_native_requested && !a6_runtime_result) {
                        ret = device_create_managed_software_node(&capture.device->dev,
                                                                  a6_native_properties, NULL);
                        if (!ret && !READ_ONCE(hcd_to_ehci(hcd)->a6_irq_fault)) {
                            usb_disable_autosuspend(capture.device);
                            a6_native_hcd = hcd;
                            a6_native_pdev = pdev;
                            /* Modules can be loaded before startup; ROM probing
                             * deferred until this runtime-ready property exists. */
                            if (capture.device->actconfig && capture.device->actconfig->interface[0]) {
                                int bind = device_reprobe(&capture.device->actconfig->interface[0]->dev);
                                pr_info("A6_EHCI_NATIVE_V1 bind_result=%d\n", bind);
                            }
                        } else if (!ret) ret = -EIO;
                    }
#endif
#if defined(A6_WIFI_USB_PREFLIGHT) || defined(A6_WIFI_USB_SCAN)
                    if (!a6_runtime_result
#ifdef A6_WIFI_NATIVE
                        && !a6_native_requested
#endif
                       )
                        a6_trial_preflight(capture.device);
#endif
#if defined(A6_WIFI_USB_RX) && !defined(A6_WIFI_USB_SCAN)
                    if (!a6_runtime_result)
                        a6_trial_bulk_rx(capture.device);
#endif
#endif
                    usb_put_dev(capture.device);
                    capture.device = NULL;
                } else {
                    a6_execute_result = -ETIMEDOUT;
                }
            }
#endif
        }
#endif
        words[4] = atomic_read(&a6_trial_irqs);
        words[5] = readl(regs + 0x60); /* Operational PORTSC4 (CAPLENGTH=0x10). */
        words[6] = READ_ONCE(hcd_to_ehci(hcd)->a6_irq_fault);
        words[7] = READ_ONCE(hcd_to_ehci(hcd)->a6_irq_status);
        words[8] = READ_ONCE(hcd_to_ehci(hcd)->a6_irq_restarts);
#ifdef A6_WIFI_NATIVE
        if (a6_native_hcd) {
            WRITE_ONCE(a6_trial_phase, 16);
            pr_info("A6_EHCI_NATIVE_V1 retained=1 runtime_ready=1\n");
            return 0;
        }
        if (a6_native_requested && !ret)
            ret = a6_runtime_result ? a6_runtime_result : -ENODEV;
#endif
        WRITE_ONCE(a6_trial_phase, 6);
        pr_info("A6_EHCI_PROGRESS_V1 remove_begin fault=%u status=%08x restarts=%u\n",
                words[6], words[7], words[8]);
        usb_remove_hcd(hcd);
        a6_runtime_inactive_resumes = hcd_to_ehci(hcd)->a6_inactive_resumes;
        pr_info("A6_HSIC_FINAL_V1 inactive_resumes=%u raw=%08x\n",
                a6_runtime_inactive_resumes, readl(regs + 0x60));
        WRITE_ONCE(a6_trial_phase, 7);
        pr_info("A6_EHCI_PROGRESS_V1 remove_end\n");
#ifdef A6_WIFI_USB_EXECUTE
        a6_trial_execute_restore();
#endif
        if (words[6])
            ret = -EIO;
        else if (!words[0])
            ret = -ENODEV;
    }
    usb_put_hcd(hcd);
unregister:
    arch_teardown_dma_ops(dev);
unregister_device:
    platform_device_unregister(pdev);
unregister_driver:
    platform_driver_unregister(&a6_trial_platform_driver);
    WRITE_ONCE(a6_trial_phase, 8);
    pr_info("A6_EHCI_PROGRESS_V1 exit result=%d\n", ret);
    return ret;
}

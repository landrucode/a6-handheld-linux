/* SPDX-License-Identifier: GPL-2.0-only */
/* Explicit ROM download only. Linux brcmfmac's 1500-byte bounce-buffer and
 * state format, with Cascadia's Apple HSIC wValue=1/no-DL_START sequence.
 * No GO, RESETCFG, runtime driver, host-ready transition or association.
 */
ssize_t a6_ehci_download(char *buf);
static int a6_download_result = -EAGAIN;
static u32 a6_download_state = ~0U, a6_download_rom_bytes;
static unsigned int a6_download_submitted, a6_download_completed;
static unsigned int a6_download_control_submitted, a6_download_control_completed;
static unsigned int a6_download_sent, a6_download_expected, a6_download_endpoint;
ssize_t a6_ehci_download(char *buf)
{
#ifdef A6_WIFI_USB_DOWNLOAD
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    return sysfs_emit(buf, "A6_WIFI_USB_DOWNLOAD_V1 enabled=%u result=%d "
        "bulk_submitted=%u bulk_completed=%u control_submitted=%u control_completed=%u "
        "sent=%u expected=%u state=%u rom_bytes=%u endpoint=%02x go_submitted=0\n",
        enabled, a6_download_result, a6_download_submitted, a6_download_completed,
        a6_download_control_submitted, a6_download_control_completed,
        a6_download_sent, a6_download_expected, a6_download_state,
        a6_download_rom_bytes, a6_download_endpoint);
}
#ifdef A6_WIFI_USB_DOWNLOAD
static unsigned int a6_download_timeout(unsigned long deadline)
{
    unsigned long now = jiffies;
    if (time_after_eq(now, deadline))
        return 0;
    return min_t(unsigned int, 1000, jiffies_to_msecs(deadline - now));
}
static int a6_download_getstate(struct usb_device *udev, __le32 *reply,
                                unsigned long deadline)
{
    unsigned int timeout = a6_download_timeout(deadline);
    int ret;
    if (!timeout)
        return -ETIMEDOUT;
    memset(reply, 0, 8);
    a6_download_control_submitted++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 0,
                          USB_DIR_IN | USB_TYPE_VENDOR | USB_RECIP_INTERFACE,
                          1, 0, reply, 8, timeout);
    if (ret != 8)
        return ret < 0 ? ret : -EMSGSIZE;
    a6_download_control_completed++;
    a6_download_state = le32_to_cpu(reply[0]);
    a6_download_rom_bytes = le32_to_cpu(reply[1]);
    return 0;
}
static void a6_trial_download(struct usb_device *udev)
{
    const struct firmware *fw = NULL;
    struct usb_host_interface *alt;
    __le32 *reply = NULL;
    u8 *chunk = NULL;
    unsigned long deadline;
    unsigned int i, endpoints = 0, length, timeout, polls;
    int actual, ret = -EPROTO;
    static const u8 product[] = {
        0x15, 0x1b, 8, 0, 's', '=', 'B', '3', 0,
        'M', '=', 'H', 'E', 'I', 'N', ' ', 'm', '=', '2', '.', '6', ' ', 'V', '=', 't',
        0, 0, 0, 0xff
    };
    if (a6_identity_result || a6_identity_fields != 0x3f ||
        a6_identity_words[0] != 0x4334 || a6_identity_words[1] != 3 ||
        a6_identity_words[2] != 0x80000 || a6_identity_words[3] != 0x60000000 ||
        a6_otp_result || a6_otp_bytes != 250 ||
        memcmp(a6_otp_data, product, sizeof(product)))
        goto result;
    /* Direct RAM-root file lookup, without userspace firmware fallback. */
    ret = request_firmware_direct(&fw, "a6-centennial-tdk.trx", &udev->dev);
    if (ret)
        goto result;
    a6_download_expected = fw->size;
    if (fw->size != A6_WIFI_FW_BYTES || fw->size < 28 ||
        get_unaligned_le32(fw->data) != 0x30524448 ||
        get_unaligned_le32(fw->data + 4) != fw->size ||
        get_unaligned_le32(fw->data + 8) != A6_WIFI_FW_CRC32 ||
        crc32_le(~0U, fw->data + 12, fw->size - 12) != A6_WIFI_FW_CRC32 ||
        get_unaligned_le32(fw->data + 12) != 0x10020 ||
        get_unaligned_le32(fw->data + 16) != 0x6ee28 ||
        get_unaligned_le32(fw->data + 20) != 0x81 ||
        get_unaligned_le32(fw->data + 24) != fw->size - 28 - 0x6ee28) {
        ret = -EBADMSG;
        goto release;
    }
    if (!usb_trylock_device(udev)) {
        ret = -EBUSY;
        goto release;
    }
    ret = -EPROTO;
    if (udev->state != USB_STATE_CONFIGURED ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a ||
        !udev->actconfig || !udev->actconfig->desc.bNumInterfaces ||
        !udev->actconfig->interface[0] ||
        !udev->actconfig->interface[0]->cur_altsetting)
        goto unlock;
    alt = udev->actconfig->interface[0]->cur_altsetting;
    if (alt->desc.bInterfaceNumber != 0)
        goto unlock;
    for (i = 0; i < alt->desc.bNumEndpoints; i++) {
        if (usb_endpoint_is_bulk_out(&alt->endpoint[i].desc)) {
            a6_download_endpoint = alt->endpoint[i].desc.bEndpointAddress;
            endpoints++;
        }
    }
    if (endpoints != 1)
        goto unlock;
    chunk = kmalloc(1500, GFP_KERNEL);
    reply = kzalloc(8, GFP_KERNEL);
    if (!chunk || !reply) {
        ret = -ENOMEM;
        goto free;
    }
    WRITE_ONCE(a6_trial_phase, 11);
    deadline = jiffies + msecs_to_jiffies(30000);
    ret = a6_download_getstate(udev, reply, deadline);
    if (ret)
        goto free;
    if (a6_download_state != 0 || a6_download_rom_bytes != 0) {
        ret = -EPROTO;
        goto free;
    }
    while (a6_download_sent < fw->size) {
        timeout = a6_download_timeout(deadline);
        if (!timeout) {
            ret = -ETIMEDOUT;
            goto free;
        }
        length = min_t(unsigned int, 1500, fw->size - a6_download_sent);
        /* Preserve Linux's no-ZLP tail adjustment. */
        if (!(length % 64))
            length -= 4;
        memcpy(chunk, fw->data + a6_download_sent, length);
        actual = 0;
        a6_download_submitted++;
        ret = usb_bulk_msg(udev, usb_sndbulkpipe(udev, a6_download_endpoint),
                           chunk, length, &actual, timeout);
        if (actual > 0 && actual <= length)
            a6_download_sent += actual;
        if (ret || actual != length) {
            if (!ret)
                ret = -EIO;
            goto free;
        }
        a6_download_completed++;
        if (a6_download_completed == 1) {
            ret = a6_download_getstate(udev, reply, deadline);
            if (ret)
                goto free;
            if (a6_download_state != 1 || a6_download_rom_bytes != a6_download_sent) {
                ret = -EPROTO;
                goto free;
            }
        }
    }
    /* Bound ROM completion polling independently of its reported progress. */
    ret = -ETIMEDOUT;
    for (polls = 0; polls < 10; polls++) {
        ret = a6_download_getstate(udev, reply, deadline);
        if (ret)
            goto free;
        if (a6_download_rom_bytes > a6_download_sent ||
            (a6_download_state != 1 && a6_download_state != 4)) {
            ret = -EPROTO;
            goto free;
        }
        if (a6_download_state == 4) {
            ret = a6_download_rom_bytes == a6_download_sent ? 0 : -EPROTO;
            goto free;
        }
        msleep(100);
    }
    ret = -ETIMEDOUT;
free:
    kfree(reply);
    kfree(chunk);
unlock:
    usb_unlock_device(udev);
release:
    release_firmware(fw);
result:
    a6_download_result = ret;
    pr_info("A6_WIFI_USB_DOWNLOAD_V1 result=%d sent=%u expected=%u state=%u rom_bytes=%u go_submitted=0\n",
            ret, a6_download_sent, a6_download_expected, a6_download_state, a6_download_rom_bytes);
}
#endif

/* Separate opt-in execution boundary. No runtime wireless driver or network
 * commands. N42 GPIO routing/polarity: verify-a6-wifi-host-ready.py.
 */
ssize_t a6_ehci_execute(char *buf);
static int a6_execute_result = -EAGAIN, a6_execute_reset = -EAGAIN;
static int a6_execute_restore = -EAGAIN, a6_execute_length = -1;
static unsigned int a6_execute_go, a6_execute_go_completed;
static unsigned int a6_execute_getver, a6_execute_writes;
static u32 a6_execute_saved, a6_execute_after, a6_execute_chip;
#ifdef A6_WIFI_USB_EXECUTE
static void __iomem *a6_execute_gpio;
#endif
ssize_t a6_ehci_execute(char *buf)
{
#ifdef A6_WIFI_USB_EXECUTE
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    return sysfs_emit(buf, "A6_WIFI_USB_EXECUTE_V1 enabled=%u result=%d "
        "go_submitted=%u go_completed=%u reset=%d getver_submitted=%u "
        "getver_length=%d chip=%08x gpio_writes=%u gpio_saved=%08x "
        "gpio_after=%08x gpio_restore=%d\n", enabled, a6_execute_result,
        a6_execute_go, a6_execute_go_completed, a6_execute_reset,
        a6_execute_getver, a6_execute_length, a6_execute_chip,
        a6_execute_writes, a6_execute_saved, a6_execute_after, a6_execute_restore);
}
#ifdef A6_WIFI_USB_EXECUTE
static int a6_execute_level(unsigned int high)
{
    u32 expected = (a6_execute_saved & ~0x6fU) | (high ? 3 : 2);
    a6_execute_writes++;
    writel(expected, a6_execute_gpio + 0xd8);
    if (readl(a6_execute_gpio + 0xd8) != expected)
        return -EIO;
    msleep(20);
    return 0;
}
static void a6_trial_execute(struct usb_device *udev)
{
    __le32 *reply;
    int ret = -EPROTO;
    /* Never execute a partial, failed or unmatched download. */
    if (a6_download_result || a6_download_state != 4 ||
        a6_download_sent != A6_WIFI_FW_BYTES ||
        a6_download_rom_bytes != A6_WIFI_FW_BYTES ||
        a6_download_completed != 305 ||
        a6_download_submitted != a6_download_completed)
        goto result;
    if (!usb_trylock_device(udev)) {
        ret = -EBUSY;
        goto result;
    }
    if (udev->state != USB_STATE_CONFIGURED ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a)
        goto unlock;
    reply = kzalloc(8, GFP_KERNEL);
    if (!reply) {
        ret = -ENOMEM;
        goto unlock;
    }
    a6_execute_gpio = ioremap(0x3fa00000, 0x1000);
    if (!a6_execute_gpio) {
        ret = -ENOMEM;
        goto free;
    }
    a6_execute_saved = readl(a6_execute_gpio + 0xd8);
    /* Stock stores a 16-bit cached pin configuration using a 32-bit MMIO
     * store. Refuse unexpected upper bits; preserve all saved other bits.
     */
    if (a6_execute_saved & 0xffff0000U) {
        ret = -EUCLEAN;
        goto free;
    }
    WRITE_ONCE(a6_trial_phase, 12);
    ret = a6_execute_level(1);
    if (ret)
        goto free;
    a6_execute_go++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 2,
                          USB_DIR_IN | USB_TYPE_VENDOR | USB_RECIP_INTERFACE,
                          1, 0, reply, 8, 1000);
    /* Count a submitted command even if its response fails: never retry GO. */
    if (ret != 8) {
        ret = ret < 0 ? ret : -EMSGSIZE;
        goto free;
    }
    a6_execute_go_completed++;
    msleep(500); /* Pinned Cascadia HSIC firmware boot wait. */
    ret = a6_execute_level(0);
    if (!ret)
        ret = a6_execute_level(1);
    if (ret)
        goto free;
    WRITE_ONCE(a6_trial_phase, 13);
    /* Linux reset requires the device mutex, held above. Descriptor changes
     * can legitimately return -ENODEV and schedule hub re-enumeration.
     * USB-core reset/teardown has its own waits, not our transfer deadline.
     */
    a6_execute_reset = usb_reset_device(udev);
    ret = a6_execute_reset;
    if (!ret || ret == -ENODEV)
        ret = -EAGAIN; /* Runtime identity still must be measured. */
free:
    kfree(reply);
unlock:
    usb_unlock_device(udev);
result:
    a6_execute_result = ret;
}
static void a6_trial_runtime_identity(struct usb_device *udev)
{
    __le32 *reply;
    int ret;
    if (!usb_trylock_device(udev)) {
        a6_execute_result = -EBUSY;
        return;
    }
    if (udev->state != USB_STATE_CONFIGURED ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a) {
        a6_execute_result = -EPROTO;
        goto unlock;
    }
    reply = kzalloc(24, GFP_KERNEL);
    if (!reply) {
        a6_execute_result = -ENOMEM;
        goto unlock;
    }
    WRITE_ONCE(a6_trial_phase, 14);
    a6_execute_getver++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 5,
                          USB_DIR_IN | USB_TYPE_VENDOR | USB_RECIP_INTERFACE,
                          1, 0, reply, 24, 1000);
    a6_execute_length = ret;
    if (ret >= 8 && ret <= 24 && !(ret & 3)) {
        a6_execute_chip = le32_to_cpu(reply[0]);
        a6_execute_result = a6_execute_chip == 0xa123 ? 0 : -EPROTO;
    } else {
        a6_execute_result = ret < 0 ? ret : -EMSGSIZE;
    }
    kfree(reply);
unlock:
    usb_unlock_device(udev);
}
static void a6_trial_execute_restore(void)
{
    if (!a6_execute_gpio)
        return;
    if (a6_execute_writes) {
        a6_execute_writes++;
        writel(a6_execute_saved, a6_execute_gpio + 0xd8);
    }
    a6_execute_after = readl(a6_execute_gpio + 0xd8);
    a6_execute_restore = a6_execute_after == a6_execute_saved ? 0 : -EUCLEAN;
    iounmap(a6_execute_gpio);
    a6_execute_gpio = NULL;
}
#endif

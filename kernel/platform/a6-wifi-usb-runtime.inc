/* SPDX-License-Identifier: GPL-2.0-only */
/* Bounded read-only BCDC control transport; no UP, SET, scan or packet TX.
 * Wire layouts follow pinned Linux brcmfmac usb.c/bcdc.c/fwil_types.h.
 */
ssize_t a6_ehci_runtime(char *buf);
static int a6_runtime_result = -EAGAIN;
static int a6_runtime_tx_length = -1, a6_runtime_rx_length = -1;
static u32 a6_runtime_last_command, a6_runtime_reply_flags, a6_runtime_reply_status, a6_runtime_reply_length;
static unsigned int a6_runtime_tx, a6_runtime_rx, a6_runtime_completed;
static u32 a6_runtime_ioctl, a6_runtime_chip, a6_runtime_chiprev;
static u32 a6_runtime_inactive_resumes, a6_runtime_version_bytes;
ssize_t a6_ehci_runtime(char *buf)
{
#ifdef A6_WIFI_USB_RUNTIME
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    return sysfs_emit(buf,
        "A6_WIFI_USB_RUNTIME_V1 enabled=%u result=%d tx=%u rx=%u completed=%u "
        "ioctl=%u chip=%u chiprev=%u version_bytes=%u inactive_resumes=%u "
        "command=%u tx_length=%d rx_length=%d flags=%08x status=%08x reply_length=%u\n",
        enabled, a6_runtime_result, a6_runtime_tx, a6_runtime_rx,
        a6_runtime_completed, a6_runtime_ioctl, a6_runtime_chip,
        a6_runtime_chiprev, a6_runtime_version_bytes, a6_runtime_inactive_resumes,
        a6_runtime_last_command, a6_runtime_tx_length, a6_runtime_rx_length,
        a6_runtime_reply_flags, a6_runtime_reply_status, a6_runtime_reply_length);
}
#ifdef A6_WIFI_USB_RUNTIME
/* Only three GET commands, with monotonically distinct request IDs. */
static int a6_runtime_query(struct usb_device *udev, u32 command, u16 id,
                            void *output, unsigned int length, bool variable)
{
    __le32 *message;
    u32 flags, reported;
    int ret;
    unsigned int size = 16 + length;

    if (!id || id > 3 || !length || length > 256 ||
        !((command == 1 && id == 1 && length == 4 && !variable) ||
          (command == 98 && id == 2 && length == 68 && !variable) ||
          (command == 262 && id == 3 && length == 256 && variable)))
        return -EINVAL;
    message = kzalloc(size, GFP_KERNEL);
    if (!message)
        return -ENOMEM;
    message[0] = cpu_to_le32(command);
    message[1] = cpu_to_le32(length);
    message[2] = cpu_to_le32((u32)id << 16); /* GET, interface0. */
    if (command == 262)
        memcpy(message + 4, "ver", 4);
    a6_runtime_last_command = command;
    a6_runtime_tx_length = a6_runtime_rx_length = -1;
    a6_runtime_reply_flags = a6_runtime_reply_status = a6_runtime_reply_length = 0;
    a6_runtime_tx++;
    ret = usb_control_msg(udev, usb_sndctrlpipe(udev, 0), 0,
                          USB_DIR_OUT | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
                          0, 0, message, size, 1000);
    a6_runtime_tx_length = ret;
    if (ret != size) {
        ret = ret < 0 ? ret : -EMSGSIZE;
        goto out;
    }
    memset(message, 0, size);
    a6_runtime_rx++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 1,
                          USB_DIR_IN | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
                          0, 0, message, size, 1000);
    a6_runtime_rx_length = ret;
    if (ret < 0)
        goto out;
    if (ret < 16 || ret > size) {
        ret = -EMSGSIZE;
        goto out;
    }
    flags = le32_to_cpu(message[2]);
    reported = le32_to_cpu(message[1]);
    a6_runtime_reply_flags = flags;
    a6_runtime_reply_length = reported;
    a6_runtime_reply_status = le32_to_cpu(message[3]);
    if (le32_to_cpu(message[0]) != command ||
        flags != ((u32)id << 16) || le32_to_cpu(message[3])) {
        ret = -EPROTO;
        goto out;
    }
    if (reported > length || reported > ret - 16 ||
        (!variable && ret != size) || (variable && ret == 16)) {
        ret = -EMSGSIZE;
        goto out;
    }
    memcpy(output, message + 4, ret - 16);
    a6_runtime_completed++;
    ret -= 16;
out:
    kfree(message);
    return ret;
}
static void a6_trial_runtime_probe(struct usb_device *udev)
{
    __le32 version, revision[17];
    unsigned char *text, *end;
    unsigned int i;
    int ret = -EPROTO;

    if (a6_execute_result || a6_execute_chip != 0xa123 ||
        a6_runtime_tx || a6_runtime_rx) {
        a6_runtime_result = -EPERM;
        return;
    }
    if (!usb_trylock_device(udev)) {
        a6_runtime_result = -EBUSY;
        return;
    }
    if (udev->state != USB_STATE_CONFIGURED ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a ||
        !udev->actconfig || udev->actconfig->desc.bNumInterfaces != 1 ||
        !udev->actconfig->interface[0] ||
        !udev->actconfig->interface[0]->cur_altsetting ||
        udev->actconfig->interface[0]->cur_altsetting->desc.bInterfaceNumber != 0)
        goto unlock;
    WRITE_ONCE(a6_trial_phase, 15);
    ret = a6_runtime_query(udev, 1, 1, &version, 4, false);
    if (ret < 0)
        goto unlock;
    a6_runtime_ioctl = le32_to_cpu(version);
    if (a6_runtime_ioctl != 1 && a6_runtime_ioctl != 2) {
        ret = -EPROTO;
        goto unlock;
    }
    ret = a6_runtime_query(udev, 98, 2, revision, sizeof(revision), false);
    if (ret < 0)
        goto unlock;
    a6_runtime_chip = le32_to_cpu(revision[11]);
    a6_runtime_chiprev = le32_to_cpu(revision[3]);
    if (a6_runtime_chip != 0x4334 || a6_runtime_chiprev != 3) {
        ret = -EPROTO;
        goto unlock;
    }
    text = kzalloc(256, GFP_KERNEL);
    if (!text) {
        ret = -ENOMEM;
        goto unlock;
    }
    ret = a6_runtime_query(udev, 262, 3, text, 256, true);
    if (ret > 0) {
        end = memchr(text, 0, ret);
        if (!end || end == text) {
            ret = -EPROTO;
        } else {
            a6_runtime_version_bytes = end - text;
            for (i = 0; i < a6_runtime_version_bytes; i++)
                if ((text[i] < 32 && text[i] != '\n' && text[i] != '\r' && text[i] != '\t') || text[i] > 126)
                    ret = -EPROTO;
            if (ret > 0)
                ret = 0;
        }
    }
    kfree(text);
unlock:
    usb_unlock_device(udev);
    a6_runtime_result = ret;
}
#endif

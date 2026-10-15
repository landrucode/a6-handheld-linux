/* SPDX-License-Identifier: GPL-2.0-only */
/* One stock-confirmed bus:loopback transaction; no radio UP or association. */
ssize_t a6_ehci_loopback(char *buf);
static int a6_loop_result = -EAGAIN, a6_loop_restore = -EAGAIN;
static unsigned int a6_loop_attempted, a6_loop_ctl_tx, a6_loop_ctl_rx;
static unsigned int a6_loop_out, a6_loop_in, a6_loop_echo, a6_loop_skipped, a6_loop_other;
static unsigned int a6_loop_before, a6_loop_after, a6_loop_bytes;
ssize_t a6_ehci_loopback(char *buf)
{
#ifdef A6_WIFI_USB_LOOPBACK
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    return sysfs_emit(buf,
        "A6_WIFI_USB_LOOPBACK_V1 enabled=%u result=%d restore=%d attempted=%u "
        "ctl_tx=%u ctl_rx=%u out=%u in=%u echo=%u skipped=%u other=%u before=%u after=%u bytes=%u radio_up=0\n",
        enabled, a6_loop_result, a6_loop_restore, a6_loop_attempted,
        a6_loop_ctl_tx, a6_loop_ctl_rx, a6_loop_out, a6_loop_in,
        a6_loop_echo, a6_loop_skipped, a6_loop_other, a6_loop_before, a6_loop_after, a6_loop_bytes);
}
#ifdef A6_WIFI_USB_LOOPBACK
#include "brcmfmac-a6-hsic.h"
/* Fixed iovar and four request IDs only. No arbitrary firmware commands. */
static noinline int a6_loop_control(struct usb_device *udev, unsigned int id,
                           bool set, u32 value, u32 *output)
{
    unsigned char *data;
    unsigned int payload = set ? 17 : 32, size = 16 + payload;
    u32 flags, reported;
    int ret;
    if (!((id == 4 && !set) || (id == 5 && set && value == 1) ||
          (id == 6 && set && value == 0) || (id == 7 && !set)))
        return -EINVAL;
    data = kzalloc(size, GFP_KERNEL);
    if (!data)
        return -ENOMEM;
    put_unaligned_le32(set ? 263 : 262, data);
    put_unaligned_le32(payload, data + 4);
    put_unaligned_le32((id << 16) | (set ? 2 : 0), data + 8);
    memcpy(data + 16, "bus:loopback", 13);
    if (set)
        put_unaligned_le32(value, data + 29);
    a6_loop_ctl_tx++;
    ret = usb_control_msg(udev, usb_sndctrlpipe(udev, 0), 0,
        USB_DIR_OUT | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
        0, 0, data, size, 1000);
    if (ret != size) {
        ret = ret < 0 ? ret : -EMSGSIZE;
        goto out;
    }
    memset(data, 0, size);
    a6_loop_ctl_rx++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 1,
        USB_DIR_IN | USB_TYPE_CLASS | USB_RECIP_INTERFACE,
        0, 0, data, size, 1000);
    if (ret < 0)
        goto out;
    if (ret < 16 || ret > size) {
        ret = -EMSGSIZE;
        goto out;
    }
    flags = get_unaligned_le32(data + 8);
    reported = get_unaligned_le32(data + 4);
    if (get_unaligned_le32(data) != (set ? 263 : 262) ||
        (flags & ~2U) != (id << 16) || get_unaligned_le32(data + 12)) {
        ret = -EPROTO;
        goto out;
    }
    if (reported > payload || reported > ret - 16 ||
        (!set && (ret < 20 || reported < 4))) {
        ret = -EMSGSIZE;
        goto out;
    }
    if (!set)
        *output = get_unaligned_le32(data + 16);
    ret = 0;
out:
    kfree(data);
    return ret;
}
static int a6_trial_loopback(struct usb_device *udev)
{
    unsigned char *tx = NULL, *rx = NULL;
    const unsigned char *frame;
    unsigned int i, n;
    u32 value;
    unsigned long started, deadline;
    unsigned int remaining;
    int ret, actual, restore;
    bool may_be_enabled = false;

    if (a6_loop_attempted || a6_runtime_result || a6_runtime_completed != 3 ||
        a6_rx_usb_result || a6_rx_frames != 1 || a6_rx_event_type != 52)
        return -EPERM;
    a6_loop_attempted = 1;
    /* TX occupies0..95; RX starts at128, outside TX cache lines. */
    tx = kzalloc(2176, GFP_KERNEL);
    if (!tx) {
        ret = -ENOMEM;
        goto done;
    }
    rx = tx + 128;
    ret = a6_loop_control(udev, 4, false, 0, &value);
    if (ret)
        goto done;
    a6_loop_before = value;
    if (value) {
        ret = -EBUSY;
        goto done;
    }
    /* Firmware may have applied the SET even if its response fails. */
    may_be_enabled = true;
    ret = a6_loop_control(udev, 5, true, 1, NULL);
    if (ret)
        goto done;
    ret = brcmf_a6_hsic_tx_header(tx, 80, 2);
    if (ret) goto done;
#ifdef A6_WIFI_USB_LOOPBACK_BAD_CHECKSUM
    /* Negative control: keep all other header/body bytes identical. */
    tx[2] ^= 1;
#endif
    tx[16] = 0x20;
    memcpy(tx + 26, "A6USBLOOP02!", 12);
    for (i = 38; i < 96; i++) tx[i] = i ^ 0xa5;
    actual = 0;
    a6_loop_out++;
    a6_rx_tx++;
    ret = usb_bulk_msg(udev, usb_sndbulkpipe(udev, a6_rx_out & 15),
                       tx, 96, &actual, 1000);
    if (ret || actual != 96) {
        ret = ret ? ret : -EMSGSIZE;
        goto done;
    }
    a6_rx_snapshot_bytes = 0;
    started = jiffies;
    deadline = started + msecs_to_jiffies(2000);
    ret = -ENOMSG;
    for (i = 0; i < 16; i++) {
        if (time_after_eq(jiffies, deadline)) { ret = -ETIMEDOUT; break; }
        remaining = jiffies_to_msecs(deadline - jiffies);
        if (!remaining) remaining = 1;
        actual = 0;
        memset(rx, 0, 2048);
        a6_loop_in++;
        ret = usb_bulk_msg(udev, usb_rcvbulkpipe(udev, a6_rx_in & 15),
                           rx, 2048, &actual, remaining);
        if (ret)
            break;
        if (actual < 0 || actual > 2048) {
            ret = -EMSGSIZE;
            break;
        }
        /* Packed journal is CPU-only; USB DMA uses a separate allocation. */
        a6_rx_snapshot[a6_loop_bytes] = actual & 255;
        a6_rx_snapshot[a6_loop_bytes + 1] = actual >> 8;
        put_unaligned_le32(jiffies_to_msecs(jiffies - started),
                           a6_rx_snapshot + a6_loop_bytes + 2);
        memcpy(a6_rx_snapshot + a6_loop_bytes + 6, rx, actual);
        a6_loop_bytes += actual + 6;
        frame = rx;
        n = actual;
        /* Stock and captured loopback path carries kind2 as well as kind0. */
        ret = a6_rx_unwrap_kind(&frame, &n, 0x2000);
        if (ret) { a6_loop_other++; ret = -ENOMSG; continue; }
        if (frame == rx + 16 && n == 80 && !memcmp(frame, tx + 16, 80)) {
            a6_loop_echo = 1;
            ret = 0;
            break;
        }
        ret = -EPROTO;
        if (n < 76 || frame[0] != 0x20 || frame[2] || frame[3] ||
            !a6_rx_event_valid(frame, n, 4, 0) ||
            a6_rx_layout_be(frame, 32, 4, 0) != 52)
            a6_loop_other++;
        else
            a6_loop_skipped++;
        ret = -ENOMSG;
    }
    /* Publish completed journal length once, after USB receives finish. */
    a6_rx_snapshot_bytes = a6_loop_bytes;
done:
    if (may_be_enabled) {
        restore = a6_loop_control(udev, 6, true, 0, NULL);
        if (!restore) {
            restore = a6_loop_control(udev, 7, false, 0, &value);
            if (!restore) {
                a6_loop_after = value;
                if (value)
                    restore = -EUCLEAN;
            }
        }
        a6_loop_restore = restore;
        if (restore)
            ret = restore;
    }
    kfree(tx);
    a6_loop_result = ret;
    return ret;
}
#endif

/* SPDX-License-Identifier: GPL-2.0-only */
/* Explicit isolated passive escan; no netdev, association or data OUT. */
#include "a6-wifi-scan-codec.h"
ssize_t a6_ehci_preflight(char *buf);
ssize_t a6_ehci_preflight_data(char *buf, loff_t off, size_t count);
static unsigned char a6_scan_journal[136000];
static unsigned int a6_scan_used, a6_scan_attempted, a6_scan_tx, a6_scan_rx;
static unsigned int a6_scan_up_attempted, a6_scan_country_attempted, a6_scan_mask_attempted, a6_scan_start_attempted;
static int a6_scan_gb_revision = -1;
static unsigned int a6_scan_receives, a6_scan_partials, a6_scan_complete, a6_scan_other;
static int a6_scan_result = -EAGAIN, a6_scan_down = -EAGAIN;
static int a6_scan_abort = -EAGAIN, a6_scan_mask_restore = -EAGAIN;
static int a6_scan_country_restore = -EAGAIN, a6_scan_mpc_restore = -EAGAIN;
static unsigned int a6_scan_mpc_attempted;
static unsigned char *a6_scan_work;
static unsigned long a6_scan_start;
static int a6_scan_save(unsigned int tag, const unsigned char *p, unsigned int bytes)
{
    if (bytes > 2048 || bytes + 8 > sizeof(a6_scan_journal) - a6_scan_used) return -ENOSPC;
    a6_scan_put(a6_scan_journal + a6_scan_used, tag, 2);
    a6_scan_put(a6_scan_journal + a6_scan_used + 2, bytes, 2);
    a6_scan_put(a6_scan_journal + a6_scan_used + 4,
        jiffies_to_msecs(jiffies - a6_scan_start), 4);
    memcpy(a6_scan_journal + a6_scan_used + 8, p, bytes); a6_scan_used += bytes + 8;
    return 0;
}
/* Fixed commands/IDs only; GET capacities also cover the iovar name. */
static int a6_scan_control(struct usb_device *dev, unsigned int id, const unsigned char *input)
{
    const char *name = NULL;
    unsigned int cmd = 262, capacity = 0, prefix = 0, size, flags, reported;
    bool set = false;
    int ret;
    switch (id) {
    case 20: case 25: case 39: name = "country"; capacity = 12; break;
    case 21: case 28: case 37: name = "event_msgs"; capacity = 32; break;
    case 23: case 35: name = "mpc"; capacity = 4; break;
    case 29: case 34: name = "mpc"; capacity = 4; set = true; break;
    case 22: name = "cur_etheraddr"; capacity = 16; break;
    case 26: cmd = 217; capacity = 260; break;
    case 24: case 38: name = "country"; capacity = 12; set = true; break;
    case 27: case 36: name = "event_msgs"; capacity = 32; set = true; break;
    case 30: case 33: cmd = id == 30 ? 2 : 3; capacity = 4; set = true; break;
    case 31: case 32: name = "escan"; capacity = id == 31 ? 80 : 72; set = true; break;
    default: return -EINVAL;
    }
    if (set && !input) return -EINVAL;
    if (name) prefix = strlen(name) + 1;
    if (set && name) cmd = 263;
    size = 16 + capacity + (set ? prefix : 0);
    memset(a6_scan_work, 0, 292);
    a6_scan_put(a6_scan_work, cmd, 4);
    a6_scan_put(a6_scan_work + 4, size - 16, 4);
    a6_scan_put(a6_scan_work + 8, (id << 16) | (set ? 2 : 0), 4);
    if (name) memcpy(a6_scan_work + 16, name, prefix);
    if (set) memcpy(a6_scan_work + 16 + prefix, input, capacity);
    if (id == 26) a6_scan_put(a6_scan_work + 16, 64, 4);
    a6_scan_tx++;
    ret = usb_control_msg(dev, usb_sndctrlpipe(dev, 0), 0,
        USB_DIR_OUT | USB_TYPE_CLASS | USB_RECIP_INTERFACE, 0, 0, a6_scan_work, size, 1000);
    if (ret != size) return ret < 0 ? ret : -EMSGSIZE;
    memset(a6_scan_work, 0, 292); a6_scan_rx++;
    ret = usb_control_msg(dev, usb_rcvctrlpipe(dev, 0), 1,
        USB_DIR_IN | USB_TYPE_CLASS | USB_RECIP_INTERFACE, 0, 0, a6_scan_work, size, 1000);
    if (ret < 0) return ret;
    if (ret > size) return -EMSGSIZE;
    if (a6_scan_save(id, a6_scan_work, ret)) return -ENOSPC;
    if (ret < 16) return -EMSGSIZE;
    flags = a6_scan_le(a6_scan_work + 8, 4); reported = a6_scan_le(a6_scan_work + 4, 4);
    if (a6_scan_le(a6_scan_work, 4) != cmd || (flags & ~(set ? 3U : 1U)) != id << 16) return -EPROTO;
    if ((flags & 1) || a6_scan_le(a6_scan_work + 12, 4)) return -EREMOTEIO;
    if (reported > size - 16 || reported > ret - 16) return -EMSGSIZE;
    if (!set && reported < capacity) return -EMSGSIZE;
    return 0;
}
static int a6_scan_receive(struct usb_device *dev, unsigned char *data)
{
    unsigned long deadline = jiffies + msecs_to_jiffies(3000);
    unsigned int i, n, offset, type, status, body;
    const unsigned char *p;
    int ret, actual, timeout;
    for (i = 0; i < 64; i++) {
        if (time_after_eq(jiffies, deadline)) return -ETIMEDOUT;
        timeout = jiffies_to_msecs(deadline - jiffies);
        if (!timeout) return -ETIMEDOUT;
        actual = 0; a6_scan_receives++;
        ret = usb_bulk_msg(dev, usb_rcvbulkpipe(dev, a6_rx_in & 15), data, 2048, &actual, timeout);
        if (actual < 0 || actual > 2048) return -EMSGSIZE;
        if (actual && a6_scan_save(0x8000 + i, data, actual)) return -ENOSPC;
        if (ret) return ret;
        if (time_after_eq(jiffies, deadline)) return -ETIMEDOUT;
        p = data; n = actual;
        if (a6_rx_unwrap(&p, &n) || n < 4 || (p[0] >> 4) != 2 || (p[2] & 15)) goto other;
        offset = 4 + p[3] * 4;
        if (offset > n || !a6_rx_event_valid(p, n, offset, 0)) goto other;
        type = a6_rx_layout_be(p, offset + 28, 4, 0);
        status = a6_rx_layout_be(p, offset + 32, 4, 0);
        body = a6_rx_layout_be(p, offset + 44, 4, 0);
        if (type != 69 && type != 26) goto other;
        if (type == 69 && status == 8) {
            ret = a6_scan_partial(p + offset + 72, body, 0x1234);
            if (ret != 1) goto other;
            a6_scan_partials++;
        } else if (status == 0) {
            /* Some firmware completion bodies are empty; no BSS claim. */
            if (body && (body < 12 || a6_scan_le(p + offset + 72, 4) < 12 ||
                a6_scan_le(p + offset + 72, 4) > body || a6_scan_le(p + offset + 76, 4) != 109 ||
                a6_scan_le(p + offset + 80, 2) != 0x1234 || a6_scan_le(p + offset + 82, 2))) goto other;
            a6_scan_complete = 1; return 0;
        } else if (status == 4) return -ECANCELED;
        else goto other;
        continue;
other:
        a6_scan_other++;
    }
    return -ENOSPC;
}
static void a6_trial_preflight(struct usb_device *dev)
{
    unsigned char original[12], mask[32], desired[32], target[12] = {'G','B',0,0,255,255,255,255,'G','B',0,0};
    unsigned char saved_mpc[4], zero[4] = {0}, request[80], word[4] = {1,0,0,0};
    unsigned short channels[3] = {0x2b01,0x2b06,0x2b0b};
    struct usb_interface *intf = NULL;
    bool country = false, events = false, up = false, scan = false;
    unsigned int i, n, have = 0;
    int ret;
    if (a6_runtime_result || a6_runtime_completed != 3 ||
        a6_runtime_ioctl != 1 || a6_runtime_chip != 0x4334 || a6_runtime_chiprev != 3) {
        a6_scan_result = -EPERM; return;
    }
    a6_scan_attempted++;
    a6_scan_tx = a6_scan_rx = a6_scan_receives = a6_scan_partials = a6_scan_complete = a6_scan_other = a6_scan_used = 0;
    a6_scan_up_attempted = a6_scan_country_attempted = a6_scan_mask_attempted = a6_scan_start_attempted = a6_scan_mpc_attempted = 0;
    a6_rx_registered = a6_rx_deregistered = a6_rx_claimed = a6_rx_disconnected = 0;
    a6_scan_abort = a6_scan_down = a6_scan_mask_restore = a6_scan_country_restore = a6_scan_mpc_restore = a6_rx_release = -EAGAIN;
    a6_scan_start = jiffies;
    ret = usb_register_driver(&a6_rx_driver, NULL, "a6_wifi_bulk_rx");
    if (ret) goto done;
    a6_rx_registered++;
    if (!usb_trylock_device(dev)) { ret = -EBUSY; goto deregister; }
    ret = a6_rx_endpoints(dev, &intf); if (ret) goto unlock;
    a6_scan_work = kzalloc(2340, GFP_KERNEL); if (!a6_scan_work) { ret = -ENOMEM; goto unlock; }
    ret = usb_driver_claim_interface(&a6_rx_driver, intf, &a6_scan_attempted); if (ret) goto free;
    a6_rx_claimed++;
    ret = a6_scan_control(dev, 20, NULL); if (ret) goto cleanup;
    memcpy(original, a6_scan_work + 16, 12);
    if (!memchr(original, 0, 4) || !memchr(original + 8, 0, 4)) { ret = -EPROTO; goto cleanup; }
    ret = a6_scan_control(dev, 21, NULL); if (ret) goto cleanup;
    memcpy(mask, a6_scan_work + 16, 32); memcpy(desired, mask, 32); desired[8] |= 1 << 5; desired[3] |= 1 << 2; desired[6] &= ~(1 << 4);
    ret = a6_scan_control(dev, 22, NULL); if (ret) goto cleanup;
    n = 0; for (i = 0; i < 6; i++) n |= a6_scan_work[16 + i];
    if (!n || (a6_scan_work[16] & 1)) { ret = -EPROTO; goto cleanup; }
    ret = a6_scan_control(dev, 23, NULL); if (ret) goto cleanup;
    memcpy(saved_mpc, a6_scan_work + 16, 4);
    country = true; a6_scan_country_attempted = 1; ret = a6_scan_control(dev, 24, target); if (ret) goto cleanup;
    ret = a6_scan_control(dev, 25, NULL); if (ret) goto cleanup;
    if (memcmp(a6_scan_work + 16, target, 4) || memcmp(a6_scan_work + 24, target + 8, 4)) { ret = -EPROTO; goto cleanup; }
    a6_scan_gb_revision = a6_scan_le(a6_scan_work + 20, 4);
    ret = a6_scan_control(dev, 26, NULL); if (ret) goto cleanup;
    n = a6_scan_le(a6_scan_work + 16, 4); if (n > 64) { ret = -EPROTO; goto cleanup; }
    for (i = 0; i < n; i++) {
        unsigned int c = a6_scan_le(a6_scan_work + 20 + i * 4, 4);
        if (c == 1) have |= 1; if (c == 6) have |= 2; if (c == 11) have |= 4;
    }
    if (have != 7) { ret = -EPROTO; goto cleanup; }
    events = true; a6_scan_mask_attempted = 1;
    ret = a6_scan_control(dev, 27, desired);
    if (!ret) ret = a6_scan_control(dev, 28, NULL);
    if (!ret && memcmp(a6_scan_work + 16, desired, 32)) ret = -EUCLEAN;
    if (ret) {
        /* If TRACE suppression is refused, preserve its original bit. */
        desired[6] = mask[6];
        ret = a6_scan_control(dev, 27, desired);
        if (!ret) ret = a6_scan_control(dev, 28, NULL);
        if (!ret && memcmp(a6_scan_work + 16, desired, 32)) ret = -EUCLEAN;
    }
    if (ret) goto cleanup;
    a6_scan_mpc_attempted = 1; ret = a6_scan_control(dev, 29, zero); if (ret) goto cleanup;
    ret = a6_scan_control(dev, 23, NULL); if (ret) goto cleanup;
    if (a6_scan_le(a6_scan_work + 16, 4)) { ret = -EUCLEAN; goto cleanup; }
    up = true; a6_scan_up_attempted = 1; ret = a6_scan_control(dev, 30, word); if (ret) goto cleanup;
    a6_scan_request(request, sizeof(request), channels, 3, 0x1234, 0);
    scan = true; a6_scan_start_attempted = 1; ret = a6_scan_control(dev, 31, request); if (ret) goto cleanup;
    ret = a6_scan_receive(dev, a6_scan_work + 292);
cleanup:
    if (scan && !a6_scan_complete) {
        a6_scan_request(request, sizeof(request), NULL, 0, 0x1234, 1);
        a6_scan_abort = a6_scan_control(dev, 32, request);
    }
    if (scan && a6_scan_complete) a6_scan_abort = 0;
    if (up) a6_scan_down = a6_scan_control(dev, 33, word);
    if (a6_scan_mpc_attempted) {
        a6_scan_mpc_restore = a6_scan_control(dev, 34, saved_mpc);
        if (!a6_scan_mpc_restore) a6_scan_mpc_restore = a6_scan_control(dev, 35, NULL);
        if (!a6_scan_mpc_restore && memcmp(a6_scan_work + 16, saved_mpc, 4)) a6_scan_mpc_restore = -EUCLEAN;
    }
    if (events) {
        a6_scan_mask_restore = a6_scan_control(dev, 36, mask);
        if (!a6_scan_mask_restore) a6_scan_mask_restore = a6_scan_control(dev, 37, NULL);
        if (!a6_scan_mask_restore && memcmp(a6_scan_work + 16, mask, 32)) a6_scan_mask_restore = -EUCLEAN;
    }
    if (country) {
        a6_scan_country_restore = a6_scan_control(dev, 38, original);
        if (!a6_scan_country_restore) a6_scan_country_restore = a6_scan_control(dev, 39, NULL);
        if (!a6_scan_country_restore && memcmp(a6_scan_work + 16, original, 12)) a6_scan_country_restore = -EUCLEAN;
    }
    usb_driver_release_interface(&a6_rx_driver, intf);
    a6_rx_release = !intf->dev.driver && !usb_get_intfdata(intf) && a6_rx_disconnected == 1 ? 0 : -EUCLEAN;
free:
    kfree(a6_scan_work); a6_scan_work = NULL;
unlock:
    usb_unlock_device(dev);
deregister:
    usb_deregister(&a6_rx_driver); a6_rx_deregistered++;
done:
    a6_scan_result = ret;
}
ssize_t a6_ehci_preflight(char *buf)
{
    return sysfs_emit(buf, "A6_WIFI_USB_SCAN_V1 enabled=1 attempted=%u result=%d tx=%u rx=%u receives=%u partials=%u complete=%u other=%u abort=%d down=%d mask_restore=%d country_restore=%d mpc_restore=%d mpc_attempted=%u release=%d registered=%u deregistered=%u bytes=%u up_attempted=%u country_attempted=%u mask_attempted=%u start_attempted=%u gb_revision=%d passive=1 association=0 bulk_out=0\n",
        a6_scan_attempted, a6_scan_result, a6_scan_tx, a6_scan_rx, a6_scan_receives,
        a6_scan_partials, a6_scan_complete, a6_scan_other, a6_scan_abort, a6_scan_down,
        a6_scan_mask_restore, a6_scan_country_restore, a6_scan_mpc_restore, a6_scan_mpc_attempted, a6_rx_release, a6_rx_registered,
        a6_rx_deregistered, a6_scan_used, a6_scan_up_attempted, a6_scan_country_attempted, a6_scan_mask_attempted, a6_scan_start_attempted, a6_scan_gb_revision);
}
ssize_t a6_ehci_preflight_data(char *buf, loff_t off, size_t count)
{
    if (off < 0) return -EINVAL;
    if (off >= a6_scan_used) return 0;
    if (count > a6_scan_used - off) count = a6_scan_used - off;
    memcpy(buf, a6_scan_journal + off, count); return count;
}

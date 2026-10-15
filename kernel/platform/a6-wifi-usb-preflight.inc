#ifndef A6_WIFI_USB_SCAN
/* SPDX-License-Identifier: GPL-2.0-only */
/* Scan prerequisites; opt-in GB setting trial, never UP/scan/bulk data/netdev. */
ssize_t a6_ehci_preflight(char *buf);
ssize_t a6_ehci_preflight_data(char *buf, loff_t off, size_t count);
static int a6_pref_result = -EAGAIN;
static int a6_pref_query_result[4] = {-EAGAIN, -EAGAIN, -EAGAIN, -EAGAIN};
static unsigned int a6_pref_attempted, a6_pref_tx, a6_pref_rx;
static unsigned int a6_pref_country_gb, a6_pref_clm_bytes, a6_pref_mac_valid, a6_pref_channels;
#ifdef A6_WIFI_USB_PREFLIGHT
static unsigned char a6_pref_data[1120];
static unsigned int a6_pref_bytes;
#ifdef A6_WIFI_USB_COUNTRY
static unsigned char a6_pref_original[12], a6_pref_readback[12];
#endif
#endif
static int a6_country_result = -EAGAIN, a6_country_restore = -EAGAIN;
static unsigned int a6_country_attempted, a6_country_sets, a6_country_gb_channels;
ssize_t a6_ehci_preflight(char *buf)
{
#ifdef A6_WIFI_USB_PREFLIGHT
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
#ifdef A6_WIFI_USB_COUNTRY
    const unsigned int country_enabled = 1;
#else
    const unsigned int country_enabled = 0;
#endif
    return sysfs_emit(buf,
        "A6_WIFI_USB_PREFLIGHT_V1 enabled=%u attempted=%u result=%d tx=%u rx=%u country=%d clm=%d mac=%d channels=%d country_gb=%u clm_bytes=%u mac_valid=%u channel_count=%u radio_up=0 set=%u bulk_out=0 country_trial_enabled=%u country_attempted=%u country_result=%d country_restore=%d gb_channels=%u\n",
        enabled, a6_pref_attempted, a6_pref_result, a6_pref_tx, a6_pref_rx,
        a6_pref_query_result[0], a6_pref_query_result[1], a6_pref_query_result[2], a6_pref_query_result[3],
        a6_pref_country_gb, a6_pref_clm_bytes, a6_pref_mac_valid, a6_pref_channels,
        a6_country_sets, country_enabled, a6_country_attempted, a6_country_result, a6_country_restore, a6_country_gb_channels);
}
ssize_t a6_ehci_preflight_data(char *buf, loff_t off, size_t count)
{
    if (off < 0) return -EINVAL;
#ifdef A6_WIFI_USB_PREFLIGHT
    if (off >= a6_pref_bytes) return 0;
    if (count > a6_pref_bytes - off) count = a6_pref_bytes - off;
    memcpy(buf, a6_pref_data + off, count);
    return count;
#else
    return 0;
#endif
}
#ifdef A6_WIFI_USB_PREFLIGHT
/* Fixed four GETs, request IDs4..7; request capacity includes each iovar name. */
static int a6_pref_exchange(struct usb_device *udev, unsigned int index, unsigned int id, const unsigned char *country)
{
    static const char * const names[3] = {"country", "clmver", "cur_etheraddr"};
    static const unsigned int capacities[4] = {12, 256, 16, 260};
    unsigned char *data, *body, *end;
    unsigned int size, capacity, i, n, used;
    u32 command, flags, reported, status;
    int ret;
    if (index >= 4) return -EINVAL;
    if (!(id == index + 4 && !country)) {
#ifdef A6_WIFI_USB_COUNTRY
        if (!((index == 0 && ((id == 8 && country) || (id == 9 && !country) ||
            (id == 11 && country) || (id == 12 && !country))) ||
            (index == 3 && id == 10 && !country))) return -EINVAL;
#else
        return -EINVAL;
#endif
    }
    capacity = capacities[index]; size = 16 + capacity;
    command = country ? 263 : index == 3 ? 217 : 262;
    if (country) { capacity = 20; size = 36; }
    data = kzalloc(size, GFP_KERNEL);
    if (!data) return -ENOMEM;
    put_unaligned_le32(command, data);
    put_unaligned_le32(capacity, data + 4);
    put_unaligned_le32((id << 16) | (country ? 2 : 0), data + 8);
    if (index < 3) memcpy(data + 16, names[index], strlen(names[index]) + 1);
    else put_unaligned_le32(64, data + 16);
    if (country) { memcpy(data + 24, country, 12); a6_country_sets++; }
    a6_pref_tx++;
    ret = usb_control_msg(udev, usb_sndctrlpipe(udev, 0), 0,
        USB_DIR_OUT | USB_TYPE_CLASS | USB_RECIP_INTERFACE, 0, 0, data, size, 1000);
    if (ret != size) { ret = ret < 0 ? ret : -EMSGSIZE; goto out; }
    memset(data, 0, size);
    a6_pref_rx++;
    ret = usb_control_msg(udev, usb_rcvctrlpipe(udev, 0), 1,
        USB_DIR_IN | USB_TYPE_CLASS | USB_RECIP_INTERFACE, 0, 0, data, size, 1000);
    if (ret < 0) goto out;
    if (ret > size) { ret = -EMSGSIZE; goto out; }
    /* Retain every completed, bounded reply before interpreting its header. */
    used = a6_pref_bytes;
    if (used + ret + 4 > sizeof(a6_pref_data)) { ret = -ENOSPC; goto out; }
    a6_pref_data[used] = id; a6_pref_data[used + 1] = 0;
    a6_pref_data[used + 2] = ret & 255; a6_pref_data[used + 3] = ret >> 8;
    memcpy(a6_pref_data + used + 4, data, ret);
    a6_pref_bytes += ret + 4;
    if (ret < 16) { ret = -EMSGSIZE; goto out; }
    flags = get_unaligned_le32(data + 8);
    reported = get_unaligned_le32(data + 4);
    status = get_unaligned_le32(data + 12);
    if (get_unaligned_le32(data) != command || (flags & ~(country ? 3U : 1U)) != (id << 16)) {
        ret = -EPROTO; goto out;
    }
    if (status || (flags & 1)) { ret = -EREMOTEIO; goto out; }
    if (reported > capacity || reported > ret - 16) { ret = -EMSGSIZE; goto out; }
    if (country) { ret = 0; goto out; }
    body = data + 16;
    ret = -EPROTO;
    switch (index) {
    case 0:
        if (reported < 12 || !memchr(body, 0, 4) || !memchr(body + 8, 0, 4)) break;
#ifdef A6_WIFI_USB_COUNTRY
        memcpy(id == 4 ? a6_pref_original : a6_pref_readback, body, 12);
#endif
        a6_pref_country_gb = body[0] == 'G' && body[1] == 'B' && !body[2];
        ret = 0; break;
    case 1:
        end = memchr(body, 0, reported);
        if (!end || end == body) break;
        a6_pref_clm_bytes = end - body;
        ret = 0; break;
    case 2:
        if (reported < 6) break;
        n = 0; for (i = 0; i < 6; i++) n |= body[i];
        a6_pref_mac_valid = n && !(body[0] & 1);
        ret = 0; break;
    case 3:
        if (reported < 4) break;
        n = get_unaligned_le32(body);
        if (n > 64 || n > (reported - 4) / 4) break;
        for (i = 0; i < n; i++) {
            unsigned int channel = get_unaligned_le32(body + 4 + i * 4);
            if (!channel || channel > 196) goto out;
        }
        a6_pref_channels = n;
        ret = 0; break;
    }
out:
    kfree(data);
    return ret;
}
static int a6_pref_query(struct usb_device *udev, unsigned int index)
{
    return a6_pref_exchange(udev, index, index + 4, NULL);
}
#ifdef A6_WIFI_USB_COUNTRY
static void a6_trial_country(struct usb_device *udev)
{
    unsigned char target[12] = {'G','B',0,0,255,255,255,255,'G','B',0,0};
    int ret, restore;
    if (a6_country_attempted || a6_pref_result) { a6_country_result = -EPERM; return; }
    a6_country_attempted = 1;
    /* The SET may apply even if OUT completion or its response fails. */
    ret = a6_pref_exchange(udev, 0, 8, target);
    if (!ret) ret = a6_pref_exchange(udev, 0, 9, NULL);
    if (!ret && (memcmp(a6_pref_readback, target, 4) || memcmp(a6_pref_readback + 8, target + 8, 4))) ret = -EPROTO;
    if (!ret) {
        ret = a6_pref_exchange(udev, 3, 10, NULL);
        if (!ret) a6_country_gb_channels = a6_pref_channels;
    }
    a6_country_result = ret;
    restore = a6_pref_exchange(udev, 0, 11, a6_pref_original);
    if (!restore) restore = a6_pref_exchange(udev, 0, 12, NULL);
    if (!restore && memcmp(a6_pref_original, a6_pref_readback, 12)) restore = -EUCLEAN;
    a6_country_restore = restore;
}
#endif
static void a6_trial_preflight(struct usb_device *udev)
{
    unsigned int i;
    int ret;
    if (a6_pref_attempted || a6_runtime_result || a6_runtime_completed != 3) {
        a6_pref_result = -EPERM; return;
    }
    a6_pref_attempted = 1;
    if (!usb_trylock_device(udev)) { a6_pref_result = -EBUSY; return; }
    a6_pref_result = 0;
    for (i = 0; i < 4; i++) {
        ret = a6_pref_query(udev, i);
        a6_pref_query_result[i] = ret;
        if (ret && !a6_pref_result) a6_pref_result = ret;
    }
#ifdef A6_WIFI_USB_COUNTRY
    if (!a6_pref_result) a6_trial_country(udev);
#endif
    usb_unlock_device(udev);
}
#endif

#endif /* !SCAN */

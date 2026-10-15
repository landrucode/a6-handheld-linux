/* SPDX-License-Identifier: GPL-2.0-only */
/* One passive runtime receive, no bulk OUT or firmware state-changing command. */
ssize_t a6_ehci_bulk_rx(char *buf);
static int a6_rx_result = -EAGAIN, a6_rx_usb_result = -EAGAIN;
static int a6_rx_release = -EAGAIN;
static unsigned int a6_rx_attempted, a6_rx_registered, a6_rx_deregistered;
static unsigned int a6_rx_claimed, a6_rx_disconnected, a6_rx_submitted;
static unsigned int a6_rx_bytes, a6_rx_in, a6_rx_out, a6_rx_mps;
static unsigned int a6_rx_tx;
static unsigned int a6_rx_frames, a6_rx_payload, a6_rx_type;
static u32 a6_rx_layout_mask, a6_rx_event_type, a6_rx_event_length;
static unsigned int a6_rx_event_version, a6_rx_wrapper_bytes;
#ifdef A6_WIFI_USB_RX
#ifdef A6_WIFI_USB_LOOPBACK
#define A6_RX_SNAPSHOT_CAPACITY 32864
#else
#define A6_RX_SNAPSHOT_CAPACITY 2048
#endif
static unsigned char a6_rx_snapshot[A6_RX_SNAPSHOT_CAPACITY];
static unsigned int a6_rx_snapshot_bytes;
#endif
ssize_t a6_ehci_bulk_rx_data(char *buf, loff_t off, size_t count);
/* Called under the enumeration mutex; immutable after the one-shot trial. */
ssize_t a6_ehci_bulk_rx_data(char *buf, loff_t off, size_t count)
{
    if (off < 0)
        return -EINVAL;
#ifdef A6_WIFI_USB_RX
    if (off >= a6_rx_snapshot_bytes)
        return 0;
    if (count > a6_rx_snapshot_bytes - off)
        count = a6_rx_snapshot_bytes - off;
    memcpy(buf, a6_rx_snapshot + off, count);
    return count;
#else
    return 0;
#endif
}
ssize_t a6_ehci_bulk_rx(char *buf)
{
#ifdef A6_WIFI_USB_RX
    const unsigned int enabled = 1;
#else
    const unsigned int enabled = 0;
#endif
    return sysfs_emit(buf,
        "A6_WIFI_USB_BULK_RX_V1 enabled=%u result=%d attempted=%u usb_result=%d "
        "registered=%u deregistered=%u claimed=%u disconnected=%u release=%d "
        "submitted=%u bytes=%u in=%02x out=%02x mps=%u frames=%u payload=%u type=%04x layout=%03x event=%u event_version=%u event_bytes=%u wrapper=%u tx=%u\n",
        enabled, a6_rx_result, a6_rx_attempted, a6_rx_usb_result,
        a6_rx_registered, a6_rx_deregistered, a6_rx_claimed,
        a6_rx_disconnected, a6_rx_release, a6_rx_submitted, a6_rx_bytes,
        a6_rx_in, a6_rx_out, a6_rx_mps, a6_rx_frames, a6_rx_payload, a6_rx_type,
        a6_rx_layout_mask, a6_rx_event_type, a6_rx_event_version, a6_rx_event_length, a6_rx_wrapper_bytes, a6_rx_tx);
}
#ifdef A6_WIFI_USB_RX
#ifdef A6_WIFI_USB_LOOPBACK
static int a6_trial_loopback(struct usb_device *udev);
#endif
/* No automatic matching or dynamic IDs. Only the verified interface is claimed. */
static int a6_rx_probe(struct usb_interface *intf, const struct usb_device_id *id)
{
    return -ENODEV;
}
static void a6_rx_disconnect(struct usb_interface *intf)
{
    a6_rx_disconnected++;
    usb_set_intfdata(intf, NULL);
}
static struct usb_driver a6_rx_driver = {
    .name = "a6-wifi-bulk-rx-trial",
    .probe = a6_rx_probe,
    .disconnect = a6_rx_disconnect,
    .no_dynamic_id = 1,
    .soft_unbind = 1, /* usb_bulk_msg has completed/cancelled before release. */
};
static int a6_rx_endpoints(struct usb_device *udev, struct usb_interface **chosen)
{
    struct usb_host_interface *alt;
    struct usb_interface *intf;
    struct usb_endpoint_descriptor *ep;
    unsigned int i, in = 0, out = 0;

    if (udev->state != USB_STATE_CONFIGURED || udev->speed != USB_SPEED_HIGH ||
        le16_to_cpu(udev->descriptor.idVendor) != 0x0a5c ||
        le16_to_cpu(udev->descriptor.idProduct) != 0xbd1a ||
        udev->descriptor.bNumConfigurations != 1 ||
        !udev->actconfig || udev->actconfig->desc.bNumInterfaces != 1)
        return -EPROTO;
    intf = udev->actconfig->interface[0];
    if (!intf || !intf->cur_altsetting)
        return -EPROTO;
    if (intf->dev.driver)
        return -EBUSY;
    alt = intf->cur_altsetting;
    if (alt->desc.bInterfaceNumber != 0 || alt->desc.bAlternateSetting != 0 ||
        alt->desc.bInterfaceClass != 0xff || alt->desc.bInterfaceSubClass != 2 ||
        alt->desc.bInterfaceProtocol != 0xff ||
        alt->desc.bNumEndpoints < 2 || alt->desc.bNumEndpoints > 4)
        return -EPROTO;
    for (i = 0; i < alt->desc.bNumEndpoints; i++) {
        ep = &alt->endpoint[i].desc;
        if (!usb_endpoint_xfer_bulk(ep))
            continue;
        if (!usb_endpoint_num(ep) || (ep->bEndpointAddress & 0x70) ||
            le16_to_cpu(ep->wMaxPacketSize) != 512)
            return -EPROTO;
        if (usb_endpoint_dir_in(ep)) {
            if (in++)
                return -EPROTO;
            a6_rx_in = ep->bEndpointAddress;
        } else {
            if (out++)
                return -EPROTO;
            a6_rx_out = ep->bEndpointAddress;
        }
    }
    if (in != 1 || out != 1)
        return -EPROTO;
    a6_rx_mps = 512;
    *chosen = intf;
    return 0;
}
/* Diagnose canonical Broadcom event envelopes at aligned prefixes0..16.
 * Bits0..4: native bytes; bits5..9: each32-bit word's bytes reversed.
 * Only exact EtherType/subtype/OUI/user-subtype and bounded event bodies match.
 * These are candidate interpretations; do not change frame acceptance.
 * No addresses, ifname or event payload are exported.
 */
static unsigned int a6_rx_layout_byte(const unsigned char *data,
                                    unsigned int index, unsigned int reversed)
{
    return data[index ^ (reversed ? 3 : 0)];
}
static u32 a6_rx_layout_be(const unsigned char *data, unsigned int index,
                           unsigned int count, unsigned int reversed)
{
    u32 value = 0;
    while (count--)
        value = (value << 8) | a6_rx_layout_byte(data, index++, reversed);
    return value;
}
/* Shared envelope bounds for passive event inspection and bounded TRACE drain. */
static noinline bool a6_rx_event_valid(const unsigned char *data,
                        unsigned int length, unsigned int offset, unsigned int reversed)
{
    unsigned int version;
    if (length < offset + 72 ||
        a6_rx_layout_be(data, offset + 12, 2, reversed) != 0x886c ||
        a6_rx_layout_be(data, offset + 14, 2, reversed) != 0x8001 ||
        a6_rx_layout_be(data, offset + 19, 3, reversed) != 0x001018 ||
        a6_rx_layout_be(data, offset + 22, 2, reversed) != 1)
        return false;
    version = a6_rx_layout_be(data, offset + 24, 2, reversed);
    return (version == 1 || version == 2) &&
        a6_rx_layout_be(data, offset + 44, 4, reversed) <= length - offset - 72;
}
#ifdef A6_WIFI_USB_LOOPBACK
static void a6_rx_inspect(const unsigned char *data, unsigned int length)
{
    /* One canonical layout; preserve metadata from its first valid event. */
    if (a6_rx_layout_mask || length > 2048 ||
        !a6_rx_event_valid(data, length, 4, 0))
        return;
    a6_rx_event_type = a6_rx_layout_be(data, 32, 4, 0);
    a6_rx_event_version = a6_rx_layout_be(data, 28, 2, 0);
    a6_rx_event_length = a6_rx_layout_be(data, 48, 4, 0);
    a6_rx_layout_mask = 2;
}
#else
static void a6_rx_inspect(const unsigned char *data, unsigned int length)
{
    unsigned int reversed, prefix, offset, version;
    u32 bytes;
    if (length > 2048)
        return;
    for (reversed = 0; reversed < 2; reversed++) {
        for (prefix = 0; prefix < 5; prefix++) {
            offset = prefix * 4;
            if (!a6_rx_event_valid(data, length, offset, reversed))
                continue;
            version = a6_rx_layout_be(data, offset + 24, 2, reversed);
            bytes = a6_rx_layout_be(data, offset + 44, 4, reversed);
            if (!a6_rx_layout_mask) {
                a6_rx_event_type = a6_rx_layout_be(data, offset + 28, 4, reversed);
                a6_rx_event_version = version;
                a6_rx_event_length = bytes;
            }
            a6_rx_layout_mask |= 1U << (reversed * 5 + prefix);
        }
    }
}
#endif
/* Stock HSIC USB header: LE flags, total length at4, checksum over16 bytes.
 * Bit15 marks its presence; bits12..14 select data/control/interrupt.
 * Accept only data and a complete single packet; never expose other fields.
 */
static noinline int a6_rx_unwrap_kind(const unsigned char **data,
                           unsigned int *length, unsigned int diagnostic_kind)
{
    const unsigned char *p = *data;
    unsigned int flags, i, sum = 0, declared;
    if (*length < 2 || *length > 2048)
        return -EMSGSIZE;
    flags = p[0] | ((unsigned int)p[1] << 8);
    if (!(flags & 0x8000))
        return 0;
    if (*length < 16)
        return -EMSGSIZE;
    if ((flags & 0x7000) && (flags & 0x7000) != diagnostic_kind)
        return -EPROTO;
    declared = p[4] | ((unsigned int)p[5] << 8);
    if (declared != *length)
        return -EMSGSIZE;
    for (i = 0; i < 16; i += 2)
        sum += p[i] | ((unsigned int)p[i + 1] << 8);
    sum = (sum + (sum >> 16)) & 0xffff;
    if (sum != 0xffff)
        return -EPROTO;
    *data += 16;
    *length -= 16;
    a6_rx_wrapper_bytes = 16;
    return 0;
}
/* Ordinary receive never admits loopback kind2. */
static int a6_rx_unwrap(const unsigned char **data, unsigned int *length)
{
    return a6_rx_unwrap_kind(data, length, 0);
}
/* BCDC data header: version2, interface0, data_offset in four-byte words.
 * Decode Ethernet envelope metadata only; no addresses or payload are exported.
 */
static int a6_rx_decode(const unsigned char *data, unsigned int length)
{
    unsigned int offset;
    if (length < 4 || length > 2048)
        return -EMSGSIZE;
    if ((data[0] >> 4) != 2 || (data[2] & 15) != 0)
        return -EPROTO;
    offset = 4 + (unsigned int)data[3] * 4;
    if (offset > length || length - offset < 14)
        return -EMSGSIZE;
    a6_rx_payload = length - offset;
    a6_rx_type = ((unsigned int)data[offset + 12] << 8) | data[offset + 13];
    a6_rx_frames++;
    return 0;
}
static void a6_trial_bulk_rx(struct usb_device *udev)
{
    struct usb_interface *intf = NULL;
    unsigned char *data = NULL;
    const unsigned char *frame;
    unsigned int frame_bytes;
    int ret, actual = 0;

    if (a6_rx_attempted || a6_runtime_result || a6_execute_result ||
        a6_runtime_completed != 3 || a6_runtime_chip != 0x4334 ||
        a6_runtime_chiprev != 3) {
        a6_rx_result = -EPERM;
        return;
    }
    a6_rx_attempted = 1;
    ret = usb_register_driver(&a6_rx_driver, NULL, "a6_wifi_bulk_rx");
    if (ret)
        goto done;
    a6_rx_registered++;
    if (!usb_trylock_device(udev)) {
        ret = -EBUSY;
        goto deregister;
    }
    ret = a6_rx_endpoints(udev, &intf);
    if (ret)
        goto unlock;
    data = kzalloc(2048, GFP_KERNEL);
    if (!data) {
        ret = -ENOMEM;
        goto unlock;
    }
    ret = usb_driver_claim_interface(&a6_rx_driver, intf, &a6_rx_attempted);
    if (ret)
        goto unlock;
    a6_rx_claimed++;
    WRITE_ONCE(a6_trial_phase, 16);
    a6_rx_submitted++;
    ret = usb_bulk_msg(udev, usb_rcvbulkpipe(udev, a6_rx_in & 15),
                       data, 2048, &actual, 2000);
    a6_rx_usb_result = ret;
    if (actual < 0 || actual > 2048) {
        ret = -EMSGSIZE;
    } else {
        a6_rx_bytes = actual;
        if (!ret) {
            memcpy(a6_rx_snapshot, data, actual);
            a6_rx_snapshot_bytes = actual;
            frame = data;
            frame_bytes = actual;
            ret = a6_rx_unwrap(&frame, &frame_bytes);
            if (!ret) {
                a6_rx_inspect(frame, frame_bytes);
                ret = a6_rx_decode(frame, frame_bytes);
            }
        }
    }
#ifdef A6_WIFI_USB_LOOPBACK
    if (!ret)
        ret = a6_trial_loopback(udev);
#endif
    usb_driver_release_interface(&a6_rx_driver, intf);
    a6_rx_release = !intf->dev.driver && !usb_get_intfdata(intf) &&
                    a6_rx_disconnected == 1 ? 0 : -EUCLEAN;
    if (a6_rx_release)
        ret = a6_rx_release;
unlock:
    kfree(data);
    usb_unlock_device(udev);
deregister:
    usb_deregister(&a6_rx_driver);
    a6_rx_deregistered++;
done:
    a6_rx_result = ret;
}
#endif

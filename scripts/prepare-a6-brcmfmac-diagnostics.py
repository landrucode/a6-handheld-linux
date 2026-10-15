"""Read-only N42 transport counters; no refill or recovery behavior changes."""

def render(source):
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('diagnostics anchor mismatch: ' + old[:80])
        source = source.replace(old, new)

    replace('#include <linux/usb.h>', '#include <linux/usb.h>\n#include <linux/atomic.h>')
    replace('\tstruct urb *a6_intr_urb;', '''\tstruct urb *a6_intr_urb;
 atomic_t a6_rx_complete, a6_rx_error, a6_rx_zero;
 atomic_t a6_rx_alloc_fail, a6_rx_submit_fail, a6_rx_last_status;
 atomic_t a6_intr_complete, a6_intr_error, a6_intr_submit_fail;
 atomic_t a6_intr_last_status;''')
    replace('\t/* zero length packets indicate usb "failure". Do not refill */', ''' atomic_inc(&devinfo->a6_rx_complete);
 atomic_set(&devinfo->a6_rx_last_status, urb->status);
 if (urb->status) atomic_inc(&devinfo->a6_rx_error);
 if (!urb->actual_length) atomic_inc(&devinfo->a6_rx_zero);
\t/* zero length packets indicate usb "failure". Do not refill */''')
    replace('\tskb = dev_alloc_skb(devinfo->bus_pub.bus_mtu);\n\tif (!skb) {', '''\tskb = dev_alloc_skb(devinfo->bus_pub.bus_mtu);
\tif (!skb) {
        atomic_inc(&devinfo->a6_rx_alloc_fail);''')
    replace('\tret = usb_submit_urb(req->urb, GFP_ATOMIC);\n\tif (ret) {\n\t\tbrcmf_usb_del_fromq', '''\tret = usb_submit_urb(req->urb, GFP_ATOMIC);
\tif (ret) {
        atomic_inc(&devinfo->a6_rx_submit_fail);
        atomic_set(&devinfo->a6_rx_last_status, ret);
\t\tbrcmf_usb_del_fromq''')
    replace(''' if (!urb->status && d->bus_pub.state == BRCMFMAC_USB_STATE_UP)
     usb_submit_urb(urb, GFP_ATOMIC);''', ''' atomic_inc(&d->a6_intr_complete);
 atomic_set(&d->a6_intr_last_status, urb->status);
 if (urb->status) atomic_inc(&d->a6_intr_error);
 if (!urb->status && d->bus_pub.state == BRCMFMAC_USB_STATE_UP) {
     int ret = usb_submit_urb(urb, GFP_ATOMIC);
     if (ret) {
         atomic_inc(&d->a6_intr_submit_fail);
         atomic_set(&d->a6_intr_last_status, ret);
     }
 }''')
    replace('static int brcmf_usb_up(struct device *dev)', '''/* Attribute lifetime is bounded by interface disconnect, before devinfo free.
 * Counters are atomic; queue lengths are sampled together under qlock.
 * Completions never print or change the upstream retirement policy.
 */
static ssize_t a6_transport_show(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
 struct brcmf_usbdev_info *d = usb_get_intfdata(to_usb_interface(dev));
 struct list_head *p;
 unsigned long flags;
 unsigned int rx_free = 0, rx_post = 0, tx_free = 0, tx_post = 0;
 if (!d || !brcmf_usb_a6(d->usbdev)) return -ENODEV;
 spin_lock_irqsave(&d->qlock, flags);
 list_for_each(p, &d->rx_freeq) rx_free++;
 list_for_each(p, &d->rx_postq) rx_post++;
 list_for_each(p, &d->tx_freeq) tx_free++;
 list_for_each(p, &d->tx_postq) tx_post++;
 spin_unlock_irqrestore(&d->qlock, flags);
 return sysfs_emit(buf,
     "state=%u rx_free=%u rx_post=%u tx_free=%u tx_post=%u "
     "rx_complete=%d rx_error=%d rx_zero=%d rx_alloc_fail=%d "
     "rx_submit_fail=%d rx_last_status=%d intr_complete=%d "
     "intr_error=%d intr_submit_fail=%d intr_last_status=%d\\n",
     d->bus_pub.state, rx_free, rx_post, tx_free, tx_post,
     atomic_read(&d->a6_rx_complete), atomic_read(&d->a6_rx_error),
     atomic_read(&d->a6_rx_zero), atomic_read(&d->a6_rx_alloc_fail),
     atomic_read(&d->a6_rx_submit_fail), atomic_read(&d->a6_rx_last_status),
     atomic_read(&d->a6_intr_complete), atomic_read(&d->a6_intr_error),
     atomic_read(&d->a6_intr_submit_fail), atomic_read(&d->a6_intr_last_status));
}
static DEVICE_ATTR_RO(a6_transport);

static int brcmf_usb_up(struct device *dev)''')
    replace('\t/* Success */\n\treturn 0;', ''' if (brcmf_usb_a6(usb)) {
     int diagnostic_ret = device_create_file(&intf->dev, &dev_attr_a6_transport);
     if (diagnostic_ret)
         brcmf_err("N42 transport counters unavailable: %d\\n", diagnostic_ret);
 }
\t/* Success */
\treturn 0;''')
    replace('\tif (devinfo) {\n\t\twait_for_completion', ''' device_remove_file(&intf->dev, &dev_attr_a6_transport);
\tif (devinfo) {
\t\twait_for_completion''')
    return source

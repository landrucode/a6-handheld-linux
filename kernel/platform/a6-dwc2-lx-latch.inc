// SPDX-License-Identifier: GPL-2.0-only
/* N42 diagnostic only: first EP0 -EAGAIN and its preceding USBRST. */
u32 a6_usb_lx_trace[9];
bool a6_usb_lx_snapshot_valid;
static atomic_t a6_usb_lx_claim = ATOMIC_INIT(0);
static u32 a6_usb_lx_last_connected;
static u32 a6_usb_lx_last_gotgctl;
static u32 a6_usb_lx_last_state;
#define A6_USB_LX_MAX_RESETS 32
struct a6_usb_lx_reset {
	unsigned long when;
	u32 gotgctl;
	u32 connected;
	u32 lx_state;
	u32 reinit;
};
static struct a6_usb_lx_reset a6_usb_lx_resets[A6_USB_LX_MAX_RESETS];
static u32 a6_usb_lx_reset_count;
static u32 a6_usb_lx_failure_reset_count;

static void a6_usb_lx_record_reset(struct dwc2_hsotg *hsotg,
				  u32 gotgctl, u32 connected,
				  bool reinit)
{
	u32 count = READ_ONCE(a6_usb_lx_reset_count);

	if (count < A6_USB_LX_MAX_RESETS) {
		struct a6_usb_lx_reset *entry = &a6_usb_lx_resets[count];

		entry->when = jiffies;
		entry->gotgctl = gotgctl;
		entry->connected = connected;
		entry->lx_state = hsotg->lx_state;
		entry->reinit = reinit;
	}
	WRITE_ONCE(a6_usb_lx_reset_count, count + 1);
	WRITE_ONCE(a6_usb_lx_last_connected, connected);
	WRITE_ONCE(a6_usb_lx_last_gotgctl, gotgctl);
	WRITE_ONCE(a6_usb_lx_last_state, hsotg->lx_state);
}

static void a6_usb_lx_record_eagain(struct dwc2_hsotg *hsotg)
{
	WRITE_ONCE(a6_usb_lx_trace[0], READ_ONCE(a6_usb_lx_trace[0]) + 1);
	if (atomic_cmpxchg(&a6_usb_lx_claim, 0, 1))
		return;

	WRITE_ONCE(a6_usb_lx_trace[1], hsotg->lx_state);
	WRITE_ONCE(a6_usb_lx_trace[2], hsotg->bus_suspended);
	WRITE_ONCE(a6_usb_lx_trace[3], dwc2_readl(hsotg, PCGCTL));
	WRITE_ONCE(a6_usb_lx_trace[4], READ_ONCE(a6_usb_lx_last_connected));
	WRITE_ONCE(a6_usb_lx_trace[5], READ_ONCE(a6_usb_lx_last_gotgctl));
	WRITE_ONCE(a6_usb_lx_trace[6], READ_ONCE(a6_usb_lx_last_state));
	WRITE_ONCE(a6_usb_lx_trace[7], dwc2_readl(hsotg, GINTMSK));
	WRITE_ONCE(a6_usb_lx_trace[8], dwc2_readl(hsotg, GINTSTS));
	WRITE_ONCE(a6_usb_lx_failure_reset_count,
		   READ_ONCE(a6_usb_lx_reset_count));
	smp_store_release(&a6_usb_lx_snapshot_valid, true);
	printk_deferred(KERN_INFO
		"a6-usb-lx-first: lx=%08x suspended=%08x pcgctl=%08x reset_connected=%08x reset_gotgctl=%08x reset_lx=%08x gintmsk=%08x gintsts=%08x\n",
		READ_ONCE(a6_usb_lx_trace[1]), READ_ONCE(a6_usb_lx_trace[2]),
		READ_ONCE(a6_usb_lx_trace[3]), READ_ONCE(a6_usb_lx_trace[4]),
		READ_ONCE(a6_usb_lx_trace[5]), READ_ONCE(a6_usb_lx_trace[6]),
		READ_ONCE(a6_usb_lx_trace[7]), READ_ONCE(a6_usb_lx_trace[8]));
}

static ssize_t a6_lx_latch_show(struct device *dev,
				struct device_attribute *attr, char *buf)
{
	ssize_t length;
	u32 count, i;

	if (!smp_load_acquire(&a6_usb_lx_snapshot_valid))
		length = sysfs_emit(buf, "valid=0 count=%u\n",
				    READ_ONCE(a6_usb_lx_trace[0]));
	else
		length = sysfs_emit(buf,
		"valid=1 count=%u lx=%08x suspended=%08x pcgctl=%08x reset_connected=%08x reset_gotgctl=%08x reset_lx=%08x gintmsk=%08x gintsts=%08x\n",
		READ_ONCE(a6_usb_lx_trace[0]), READ_ONCE(a6_usb_lx_trace[1]),
		READ_ONCE(a6_usb_lx_trace[2]), READ_ONCE(a6_usb_lx_trace[3]),
		READ_ONCE(a6_usb_lx_trace[4]), READ_ONCE(a6_usb_lx_trace[5]),
		READ_ONCE(a6_usb_lx_trace[6]), READ_ONCE(a6_usb_lx_trace[7]),
		READ_ONCE(a6_usb_lx_trace[8]));
	count = READ_ONCE(a6_usb_lx_reset_count);
	length += sysfs_emit_at(buf, length,
		"reset_total=%u failure_after_reset=%u stored=%u\n",
		count, READ_ONCE(a6_usb_lx_failure_reset_count),
		min(count, (u32)A6_USB_LX_MAX_RESETS));
	for (i = 0; i < min(count, (u32)A6_USB_LX_MAX_RESETS); i++) {
		struct a6_usb_lx_reset *entry = &a6_usb_lx_resets[i];

		length += sysfs_emit_at(buf, length,
			"reset[%u] jiffies=%lu gotgctl=%08x connected=%u lx=%u reinit=%u\n",
			i + 1, READ_ONCE(entry->when),
			READ_ONCE(entry->gotgctl), READ_ONCE(entry->connected),
			READ_ONCE(entry->lx_state), READ_ONCE(entry->reinit));
	}
	return length;
}
static DEVICE_ATTR_RO(a6_lx_latch);

static struct attribute *a6_usb_lx_attrs[] = {
	&dev_attr_a6_lx_latch.attr,
	NULL,
};
static const struct attribute_group a6_usb_lx_group = {
	.attrs = a6_usb_lx_attrs,
};

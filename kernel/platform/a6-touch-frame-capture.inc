// SPDX-License-Identifier: GPL-2.0-only
/* Bounded N42 frame capture. No input device until live framing is known. */
static u8 a6_frame_tx[838], a6_frame_rx[838], a6_frame_saved[838];
static unsigned int a6_frame_attempts, a6_frame_valid, a6_frame_contacts;
static unsigned int a6_frame_saved_bytes, a6_frame_bad, a6_frame_atn_changes;
static u8 a6_frame_length_replies[8][16];
static unsigned int a6_frame_length_saved, a6_frame_rejected_length;
static int a6_frame_result;

static int a6_frame_capture_run(u32 cs)
{
	unsigned long deadline = jiffies + msecs_to_jiffies(20000);
	u32 previous = readl(a6_touch_gpio + A6_TOUCH_ATN), atn_sample;
	unsigned int i, length, wire, payload, header, count, stride;
	u16 sum;
	u8 seq = 1, reply[16], command;
	int ret = 0;
#ifdef A6_TOUCH_NATIVE_INPUT
	a6_touch_trace_begin();
#endif
	if (a6_report_meta_result[1] || a6_report_meta_length[1] < 5)
		return -EPROTO;
	/* Sensor-info BCD is big-endian; the N42 live report gives 0x0266. */
	command = ((a6_report_metadata[1][6] << 8) |
		   a6_report_metadata[1][7]) > 0x23 ? 0xeb : 0xea;
	pr_info("a6-touch-frame: attended 20-second capture starting cmd=%02x\n", command);
	while (time_before(jiffies, deadline) && a6_frame_attempts < 1000) {
		atn_sample = readl(a6_touch_gpio + A6_TOUCH_ATN);
		if (atn_sample != previous) a6_frame_atn_changes++;
		previous = atn_sample;
		memset(a6_frame_tx, 0, sizeof(a6_frame_tx));
		a6_frame_tx[0] = command;
		a6_frame_tx[1] = seq;
		a6_report_checksum(a6_frame_tx);
		a6_frame_attempts++;
		ret = a6_fw_spi_xfer(a6_frame_tx, 16, reply, 16, 100, cs);
		if (ret) break;
		if (a6_frame_length_saved < ARRAY_SIZE(a6_frame_length_replies))
			memcpy(a6_frame_length_replies[a6_frame_length_saved++], reply, 16);
		/* N42 deviceReadFrameLength checks the high nibble, not exact E1. */
		if ((reply[0] & 0xf0) != 0xe0 || !a6_report_reply_valid(reply, reply[0])) {
			a6_frame_rejected_length++;
			goto bad;
		}
		length = reply[1] | (reply[2] << 8);
		if (!length) goto next;
		if (length < 2 || length > a6_report_max_packet - 5 || length > 833) goto bad;
		wire = length + 5;
		memset(a6_frame_tx, 0, sizeof(a6_frame_tx));
		a6_frame_tx[0] = command;
		a6_frame_tx[1] = seq;
		a6_frame_tx[2] = 1;
		sum = command + seq + 1;
		a6_frame_tx[wire - 2] = sum;
		a6_frame_tx[wire - 1] = sum >> 8;
		ret = a6_fw_spi_xfer(a6_frame_tx, wire, a6_frame_rx, wire, 100, cs);
		if (ret) break;
		if ((a6_frame_rx[0] != 0xea && a6_frame_rx[0] != command) || a6_frame_rx[1] != seq ||
		    (a6_frame_rx[2] | (a6_frame_rx[3] << 8)) != length) goto bad;
		sum = 0;
		for (i = 0; i < 5; i++) sum += a6_frame_rx[i];
		if ((u8)sum) goto bad;
		sum = 0;
		for (i = 5; i < wire - 2; i++) sum += a6_frame_rx[i];
		if (a6_frame_rx[wire - 2] != (u8)sum || a6_frame_rx[wire - 1] != (u8)(sum >> 8)) goto bad;
		seq = seq == 1 ? 2 : 1;
		payload = length - 2;
		if (payload < 24 || (a6_frame_rx[5] != 0x43 && a6_frame_rx[5] != 0x44)) goto bad;
		header = a6_frame_rx[7];
		count = a6_frame_rx[21];
		stride = a6_frame_rx[22];
		if (header < 24 || header > payload || count > 10 ||
		    (count && (stride < 30 || count > (payload - header) / stride))) goto bad;
		a6_frame_valid++;
		if (!a6_frame_saved_bytes || count > a6_frame_contacts) {
			memcpy(a6_frame_saved, a6_frame_rx, wire);
			a6_frame_saved_bytes = wire;
			a6_frame_contacts = count;
		}
		goto next;
bad:
		a6_frame_bad++;
next:
		msleep(20);
	}
	a6_frame_result = ret;
	pr_info("a6-touch-frame: result=%d valid=%u contacts=%u bad=%u\n", ret,
		a6_frame_valid, a6_frame_contacts, a6_frame_bad);
	return ret;
}

static ssize_t a6_frame_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	unsigned int i, j;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, "A6_TOUCH_FRAME_CAPTURE_V1 result=%d attempts=%u valid=%u contacts=%u bad=%u atn_changes=%u bytes=%u\nframe=",
		a6_frame_result, a6_frame_attempts, a6_frame_valid, a6_frame_contacts,
		a6_frame_bad, a6_frame_atn_changes, a6_frame_saved_bytes);
	for (i = 0; i < a6_frame_saved_bytes; i++) n += sysfs_emit_at(buf, n, "%02x", a6_frame_saved[i]);
	n += sysfs_emit_at(buf, n, "\nlength_rejected=%u\n", a6_frame_rejected_length);
	for (j = 0; j < a6_frame_length_saved; j++) {
		n += sysfs_emit_at(buf, n, "length_reply_%u=", j);
		for (i = 0; i < 16; i++) n += sysfs_emit_at(buf, n, "%02x", a6_frame_length_replies[j][i]);
		n += sysfs_emit_at(buf, n, "\n");
	}
	mutex_unlock(&a6_touch_lock);
	return n;
}
static struct kobj_attribute a6_frame_status_attr = __ATTR(status, 0400, a6_frame_status_show, NULL);
static struct attribute *a6_frame_attrs[] = { &a6_frame_status_attr.attr, NULL };
static const struct attribute_group a6_frame_group = { .name = "a6_touch_frames", .attrs = a6_frame_attrs };
static int __init a6_frame_init(void) { return sysfs_create_group(firmware_kobj, &a6_frame_group); }
late_initcall(a6_frame_init);

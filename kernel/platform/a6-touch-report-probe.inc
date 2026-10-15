// SPDX-License-Identifier: GPL-2.0-only
/* N42 only: bounded, read-only Z2 report-framing probe after fixed upload. */
static bool a6_report_group_ready;
static unsigned int a6_report_stage;
static int a6_report_result;
static u8 a6_report_e2_first[16], a6_report_e2_second[16];
static u8 a6_report_ea[16], a6_report_eb[16];
#ifdef A6_TOUCH_E3_INFO
static u8 a6_report_e3_first[16], a6_report_e3_second[16];
static u8 a6_report_e3_error;
static u16 a6_report_e3_length;
#endif
#ifdef A6_TOUCH_E2_RETRY
static u8 a6_report_e2_replies[4][16];
static unsigned int a6_report_e2_attempts;
#endif
static u32 a6_report_atn[4];
static unsigned int a6_report_max_packet;
static u8 a6_report_interface;
#ifdef A6_TOUCH_FRAME_CAPTURE
static int a6_frame_capture_run(u32 cs);
#endif
#ifdef A6_TOUCH_REPORT_METADATA
static const u8 a6_report_ids[] = {0xd1, 0xd3, 0xd0, 0xa1, 0xd9};
static u8 a6_report_metadata[5][838], a6_report_meta_tx[838];
static u16 a6_report_meta_length[5];
static int a6_report_meta_result[5];
#endif

static void a6_report_checksum(u8 *packet)
{
	unsigned int i;
	u16 sum = 0;

	for (i = 0; i < 14; i++)
		sum += packet[i];
	packet[14] = sum;
	packet[15] = sum >> 8;
}

static bool a6_report_reply_valid(const u8 *packet, u8 cmd)
{
	u16 sum = 0;
	unsigned int i;

	if (packet[0] != cmd)
		return false;
	for (i = 0; i < 14; i++)
		sum += packet[i];
	return packet[14] == (u8)sum && packet[15] == (u8)(sum >> 8);
}

#ifdef A6_TOUCH_REPORT_METADATA
static int a6_report_metadata_run(u32 cs)
{
	unsigned int i, j, length, wire, attempt;
	u16 sum;
	u8 info[16];
	int ret = 0;
	for (i = 0; i < ARRAY_SIZE(a6_report_ids); i++) {
		for (attempt = 0; attempt < 4; attempt++) {
			memset(a6_report_meta_tx, 0, sizeof(a6_report_meta_tx));
			a6_report_meta_tx[0] = 0xe3;
			a6_report_meta_tx[1] = a6_report_ids[i];
			a6_report_checksum(a6_report_meta_tx);
			ret = a6_fw_spi_xfer(a6_report_meta_tx, 16, info, 16, 250, cs);
			if (ret) break;
			udelay(25);
			ret = a6_fw_spi_xfer(a6_report_meta_tx, 16, info, 16, 250, cs);
			if (ret) break;
			if (a6_report_reply_valid(info, 0xe3) && info[1] == a6_report_ids[i]) break;
			ret = -EPROTO;
		}
		if (ret) goto record;
		length = info[3] | (info[4] << 8);
		if (info[2] || !length || length > a6_report_max_packet - 5 || length > 833) {
			ret = -EMSGSIZE;
			goto record;
		}
		a6_report_meta_length[i] = length;
		wire = length < 12 ? 16 : length + 5;
		memset(a6_report_meta_tx, 0, sizeof(a6_report_meta_tx));
		a6_report_meta_tx[0] = length < 12 ? 0xe6 : 0xe7;
		a6_report_meta_tx[1] = a6_report_ids[i];
		a6_report_meta_tx[3] = length;
		a6_report_meta_tx[4] = length >> 8;
		sum = a6_report_meta_tx[0] + a6_report_meta_tx[1] + a6_report_meta_tx[3] + a6_report_meta_tx[4];
		a6_report_meta_tx[14] = sum;
		a6_report_meta_tx[15] = sum >> 8;
		ret = a6_fw_spi_xfer(a6_report_meta_tx, 16, info, 16, 250, cs);
		if (ret) goto record;
		udelay(25);
		a6_report_meta_tx[2] = 1;
		if (length >= 12) {
			a6_report_meta_tx[14] = a6_report_meta_tx[15] = 0;
			a6_report_meta_tx[wire - 2] = sum;
			a6_report_meta_tx[wire - 1] = sum >> 8;
		}
		ret = a6_fw_spi_xfer(a6_report_meta_tx, wire, a6_report_metadata[i], wire, 250, cs);
		if (ret) goto record;
		sum = 0;
		for (j = 0; j < wire - 2; j++) sum += a6_report_metadata[i][j];
		if (a6_report_metadata[i][0] != a6_report_meta_tx[0] ||
		    a6_report_metadata[i][1] != a6_report_ids[i] ||
		    a6_report_metadata[i][wire - 2] != (u8)sum ||
		    a6_report_metadata[i][wire - 1] != (u8)(sum >> 8)) ret = -EPROTO;
record:
		a6_report_meta_result[i] = ret;
		/* Preserve every report result; transport faults stop further traffic. */
		if (ret && ret != -EPROTO && ret != -EMSGSIZE) return ret;
	}
	return 0;
}
#endif

static int a6_report_probe_run(u32 cs)
{
	u8 request[16] = {0};
	unsigned int attempt;
	int ret;

	if (!a6_report_group_ready)
		return -ENODEV;
	a6_report_stage = 0;
	a6_report_atn[0] = readl(a6_touch_gpio + A6_TOUCH_ATN);
#ifdef A6_TOUCH_CORRECT_EXEC_ADDR
	msleep(40); /* stock IOSleep(0x28) after successful N1 execute */
#endif
	request[0] = 0xe2;
	a6_report_checksum(request);
	for (attempt = 0; attempt <
#ifdef A6_TOUCH_E2_RETRY
		ARRAY_SIZE(a6_report_e2_replies);
#else
		1;
#endif
		attempt++) {
	ret = a6_fw_spi_xfer(request, 16, a6_report_e2_first, 16, 2000, cs);
	if (ret)
		goto out;
	a6_report_stage = 1;
#ifndef A6_TOUCH_E2_RETRY
	msleep(3);
#endif
	ret = a6_fw_spi_xfer(request, 16, a6_report_e2_second, 16, 2000, cs);
	if (ret)
		goto out;
	a6_report_stage = 2;
	a6_report_atn[1] = readl(a6_touch_gpio + A6_TOUCH_ATN);
	#ifdef A6_TOUCH_E2_RETRY
	memcpy(a6_report_e2_replies[attempt], a6_report_e2_second, 16);
	a6_report_e2_attempts = attempt + 1;
	#endif
	if (a6_report_reply_valid(a6_report_e2_second, 0xe2))
		break;
	if (attempt + 1 ==
#ifdef A6_TOUCH_E2_RETRY
		ARRAY_SIZE(a6_report_e2_replies)) {
#else
		1) {
#endif
		ret = -EPROTO;
		goto out;
	}
	msleep(3);
	}
	a6_report_interface = a6_report_e2_second[2];
	a6_report_max_packet = a6_report_e2_second[3] |
		(a6_report_e2_second[4] << 8);
	if (a6_report_max_packet < 16 || a6_report_max_packet > 4000) {
		ret = -EMSGSIZE;
		goto out;
	}
#ifdef A6_TOUCH_REPORT_METADATA
	if (a6_report_max_packet > 838) {
		ret = -EMSGSIZE;
		goto out;
	}
#endif
#ifdef A6_TOUCH_E3_INFO
	/* Stock Z2 getReportInfo(MT_INFO_FAMILYID=0xd1): two fixed transfers. */
	memset(request, 0, sizeof(request));
	request[0] = 0xe3;
	request[1] = 0xd1;
	a6_report_checksum(request);
	ret = a6_fw_spi_xfer(request, 16, a6_report_e3_first, 16, 2000, cs);
	if (ret)
		goto out;
	a6_report_stage = 3;
	udelay(25);
	ret = a6_fw_spi_xfer(request, 16, a6_report_e3_second, 16, 2000, cs);
	if (ret)
		goto out;
	a6_report_stage = 4;
	if (!a6_report_reply_valid(a6_report_e3_second, 0xe3) ||
	    a6_report_e3_second[1] != 0xd1) {
		ret = -EPROTO;
		goto out;
	}
	a6_report_e3_error = a6_report_e3_second[2];
	a6_report_e3_length = a6_report_e3_second[3] |
		(a6_report_e3_second[4] << 8);
	if (a6_report_e3_error || !a6_report_e3_length ||
	    a6_report_e3_length > a6_report_max_packet) {
		ret = -EMSGSIZE;
		goto out;
	}
#ifdef A6_TOUCH_REPORT_METADATA
	ret = a6_report_metadata_run(cs);
#ifdef A6_TOUCH_FRAME_CAPTURE
	if (!ret)
#ifdef A6_TOUCH_NATIVE_INPUT
		if (!a6_native_requested)
#endif
			ret = a6_frame_capture_run(cs);
#endif
#endif
	goto out;
#else
	memset(request, 0, sizeof(request));
	request[0] = 0xea;
	request[1] = 1;
	a6_report_checksum(request);
	ret = a6_fw_spi_xfer(request, 16, a6_report_ea, 16, 2000, cs);
	if (ret)
		goto out;
	a6_report_stage = 3;
	a6_report_atn[2] = readl(a6_touch_gpio + A6_TOUCH_ATN);
	/* The stock BCD-dependent EA/EB choice is not known until report info. */
	request[0] = 0xeb;
	a6_report_checksum(request);
	ret = a6_fw_spi_xfer(request, 16, a6_report_eb, 16, 2000, cs);
	if (ret)
		goto out;
	a6_report_stage = 4;
	a6_report_atn[3] = readl(a6_touch_gpio + A6_TOUCH_ATN);
#endif
out:
	a6_report_result = ret;
	pr_info("a6-touch-report: stage=%u result=%d interface=%u max_packet=%u\n",
		a6_report_stage, ret, a6_report_interface, a6_report_max_packet);
	return ret;
}

static ssize_t a6_report_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
#ifdef A6_TOUCH_REPORT_METADATA
	unsigned int i;
#endif

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_TOUCH_N42_REPORT_PROBE_V1 stage=%u result=%d interface=%u max_packet=%u atn=%08x,%08x,%08x,%08x\n"
		"e2_first=%16phN e2_second=%16phN ea=%16phN eb=%16phN\n",
		a6_report_stage, a6_report_result, a6_report_interface,
		a6_report_max_packet, a6_report_atn[0], a6_report_atn[1],
		a6_report_atn[2], a6_report_atn[3], a6_report_e2_first,
		a6_report_e2_second, a6_report_ea, a6_report_eb);
	#ifdef A6_TOUCH_E3_INFO
	n += sysfs_emit_at(buf, n,
		"e3_first=%16phN e3_second=%16phN e3_error=%u e3_length=%u\n",
		a6_report_e3_first, a6_report_e3_second, a6_report_e3_error,
		a6_report_e3_length);
	#endif
#ifdef A6_TOUCH_REPORT_METADATA
	for (i = 0; i < ARRAY_SIZE(a6_report_ids); i++)
		n += sysfs_emit_at(buf, n, "report_id=%02x length=%u result=%d first16=%16phN\n",
			a6_report_ids[i], a6_report_meta_length[i], a6_report_meta_result[i],
			a6_report_metadata[i]);
#endif
	#ifdef A6_TOUCH_E2_RETRY
	n += sysfs_emit_at(buf, n, "e2_attempts=%u second_replies=%16phN,%16phN,%16phN,%16phN\n",
		a6_report_e2_attempts, a6_report_e2_replies[0],
		a6_report_e2_replies[1], a6_report_e2_replies[2],
		a6_report_e2_replies[3]);
	#endif
	mutex_unlock(&a6_touch_lock);
	return n;
}
static struct kobj_attribute a6_report_status_attr =
	__ATTR(status, 0400, a6_report_status_show, NULL);
static struct attribute *a6_report_attrs[] = {
	&a6_report_status_attr.attr, NULL,
};
static const struct attribute_group a6_report_group = {
	.name = "a6_touch_report_n42", .attrs = a6_report_attrs,
};
static int __init a6_report_init(void)
{
	int ret;

	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_spi)
		return -ENODEV;
	ret = sysfs_create_group(firmware_kobj, &a6_report_group);
	a6_report_group_ready = !ret;
	return ret;
}
late_initcall(a6_report_init);

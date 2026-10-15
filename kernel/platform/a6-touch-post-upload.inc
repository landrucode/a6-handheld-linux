// SPDX-License-Identifier: GPL-2.0-only
/* Fixed N42 post-upload N1 sequence. Compiled only in touch-post-n42. */
static bool a6_post_group_ready;
static unsigned int a6_post_stage;
static int a6_post_result;
static u32 a6_post_version[2];
#ifdef A6_TOUCH_CLK32_ENABLE
static u8 a6_post_read_rx[2][8], a6_post_write_ack[5][2];
#else
static u8 a6_post_read_rx[2][8], a6_post_write_ack[4][2];
#endif
static u8 a6_post_start_rx[2], a6_post_start_ack[2], a6_post_final_rx[12];

/* Stock N1 packs each 32-bit argument as low BE16, then high BE16. */
static void a6_post_word(u8 *dst, u32 value)
{
	dst[0] = value >> 8;
	dst[1] = value;
	dst[2] = value >> 24;
	dst[3] = value >> 16;
}

static void a6_post_sum(u8 *packet, unsigned int argument_bytes)
{
	unsigned int i;
	u16 sum = 0;

	for (i = 2; i < 2 + argument_bytes; i++)
		sum += packet[i];
	packet[2 + argument_bytes] = sum >> 8;
	packet[3 + argument_bytes] = sum;
}

static int a6_post_read(u32 address, unsigned int slot, u32 cs)
{
	static const u8 query[] = {0x1a, 0xa1, 0x18, 0xe1,
		0x18, 0xe1, 0x18, 0xe1};
	u8 request[8], response[8];
	int ret;

	if (slot >= ARRAY_SIZE(a6_post_version))
		return -EINVAL;
	memset(request, 0, sizeof(request));
	request[0] = 0x1c;
	request[1] = 0x73;
	a6_post_word(request + 2, address);
	a6_post_sum(request, 4);
	ret = a6_fw_spi_xfer(request, sizeof(request), response,
			sizeof(response), 2000, cs);
	if (ret)
		return ret;
	ret = a6_fw_spi_xfer(query, sizeof(query), a6_post_read_rx[slot],
			sizeof(a6_post_read_rx[slot]), 2000, cs);
	if (ret)
		return ret;
	a6_post_version[slot] = (a6_post_read_rx[slot][2] << 8) |
		a6_post_read_rx[slot][3] |
		(a6_post_read_rx[slot][4] << 24) |
		(a6_post_read_rx[slot][5] << 16);
	return 0;
}

static int a6_post_write(u32 address, u32 value, unsigned int slot, u32 cs)
{
	static const u8 ack_request[] = {0x1a, 0xa1};
	u8 request[16], response[16];
	int ret;

	if (slot >= ARRAY_SIZE(a6_post_write_ack))
		return -EINVAL;
	memset(request, 0, sizeof(request));
	request[0] = 0x1e;
	request[1] = 0x33;
	a6_post_word(request + 2, address);
	a6_post_word(request + 6, U32_MAX);
	a6_post_word(request + 10, value);
	a6_post_sum(request, 12);
	ret = a6_fw_spi_xfer(request, sizeof(request), response,
			sizeof(response), 2000, cs);
	if (ret)
		return ret;
	ret = a6_fw_spi_xfer(ack_request, sizeof(ack_request),
			a6_post_write_ack[slot], 2, 2000, cs);
	if (!ret && ((a6_post_write_ack[slot][0] << 8) |
			a6_post_write_ack[slot][1]) != 0x4ad1)
		ret = -EPROTO;
	return ret;
}

static int a6_post_run(u32 cs)
{
	static const u8 start[] = {0x1f, 0x01};
	static const u8 ack_request[] = {0x1a, 0xa1};
	u8 final[12];
	u32 mode;
	int ret;

	if (!a6_post_group_ready)
		return -ENODEV;
	a6_post_stage = 0;
	ret = a6_post_read(0x10008ffc, 0, cs);
	if (ret)
		goto out;
	a6_post_stage = 1;
	ret = a6_post_write(0x000016e4, 0x1000300c, 0, cs);
	if (ret)
		goto out;
	a6_post_stage = 2;
	ret = a6_post_write(0x1000305c, 0x20, 1, cs);
	if (ret)
		goto out;
	a6_post_stage = 3;
	ret = a6_post_write(0x10003058, 6, 2, cs);
	if (ret)
		goto out;
	a6_post_stage = 4;
	mode = a6_post_version[0] == 0x434d11a0 ? 2 : 3;
	ret = a6_post_write(0x10003000, mode, 3, cs);
	if (ret)
		goto out;
	a6_post_stage = 5;
#ifdef A6_TOUCH_CLK32_ENABLE
	/* N42 personality clk32-clock-enable-addr/val; stock conditional slot. */
	ret = a6_post_write(0x10003518, 1, 4, cs);
	if (ret)
		goto out;
#endif
	ret = a6_post_read(0x10003800, 1, cs);
	if (ret)
		goto out;
	a6_post_stage = 6;
	ret = a6_fw_spi_xfer(start, sizeof(start), a6_post_start_rx,
			sizeof(a6_post_start_rx), 2000, cs);
	if (ret)
		goto out;
	a6_post_stage = 7;
	msleep(65); /* stock IOSleep(0x41) after the 1f01 transaction */
	ret = a6_fw_spi_xfer(ack_request, sizeof(ack_request),
			a6_post_start_ack, 2, 2000, cs);
	if (ret)
		goto out;
	a6_post_stage = 8;
	memset(final, 0, sizeof(final));
	final[0] = 0x1d;
	final[1] = 0x53;
#ifdef A6_TOUCH_CORRECT_EXEC_ADDR
	a6_post_word(final + 2, 0x10003400);
#else
	a6_post_word(final + 2, 0x10001800);
#endif
	final[7] = 1;
	a6_post_sum(final, 8);
	ret = a6_fw_spi_xfer(final, sizeof(final), a6_post_final_rx,
			sizeof(a6_post_final_rx), 2000, cs);
	if (!ret)
		a6_post_stage = 9;
out:
	a6_post_result = ret;
	pr_info("a6-touch-post: stage=%u result=%d version=%08x ack=%2phN\n",
		a6_post_stage, ret, a6_post_version[0],
		a6_post_write_ack[3]);
	return ret;
}

static ssize_t a6_post_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	unsigned int i;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_TOUCH_N42_POST_V1 stage=%u result=%d version0=%08x version1=%08x read0=%8phN read1=%8phN start_rx=%2phN start_ack=%2phN final_rx=%12phN\n",
		a6_post_stage, a6_post_result, a6_post_version[0],
		a6_post_version[1], a6_post_read_rx[0], a6_post_read_rx[1],
		a6_post_start_rx, a6_post_start_ack, a6_post_final_rx);
	for (i = 0; i < ARRAY_SIZE(a6_post_write_ack); i++)
		n += sysfs_emit_at(buf, n, "write%u_ack=%2phN\n",
			i, a6_post_write_ack[i]);
	mutex_unlock(&a6_touch_lock);
	return n;
}
static struct kobj_attribute a6_post_status_attr =
	__ATTR(status, 0400, a6_post_status_show, NULL);
static struct attribute *a6_post_attrs[] = {
	&a6_post_status_attr.attr, NULL,
};
static const struct attribute_group a6_post_group = {
	.name = "a6_touch_post_n42", .attrs = a6_post_attrs,
};
static int __init a6_post_init(void)
{
	int ret;

	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_spi)
		return -ENODEV;
	ret = sysfs_create_group(firmware_kobj, &a6_post_group);
	a6_post_group_ready = !ret;
	return ret;
}
late_initcall(a6_post_init);

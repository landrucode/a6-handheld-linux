// SPDX-License-Identifier: GPL-2.0-only
/* N42 factory calibration from private live DT capture, fixed at build time. */
static bool a6_cal_group_ready;
static unsigned int a6_cal_stage;
static int a6_cal_result;
static u8 a6_cal_ack[3][2];

static int a6_cal_packet(const u8 *packet, unsigned int length,
		unsigned int slot, u32 cs)
{
	static const u8 ack_request[] = {0x1a, 0xa1};
	int ret;

	if (!packet || slot >= ARRAY_SIZE(a6_cal_ack) ||
	    length < 16 || length > 1024 ||
	    packet[0] != 0x18 || packet[1] != 0xe1)
		return -EINVAL;
	ret = a6_fw_spi_xfer(packet, length, NULL, 0, 4000, cs);
	if (ret)
		return ret;
	ret = a6_fw_spi_xfer(ack_request, sizeof(ack_request),
			a6_cal_ack[slot], 2, 2000, cs);
	if (!ret && ((a6_cal_ack[slot][0] << 8) |
			a6_cal_ack[slot][1]) != 0x4bc1)
		ret = -EPROTO;
	return ret;
}

static int a6_cal_run(u32 cs)
{
	int ret;

	if (!a6_cal_group_ready)
		return -ENODEV;
	a6_cal_stage = 0;
	ret = a6_cal_packet(a6_n42_pxcl_0, sizeof(a6_n42_pxcl_0), 0, cs);
	if (ret)
		goto out;
	a6_cal_stage = 1;
	ret = a6_cal_packet(a6_n42_mtcl_0, sizeof(a6_n42_mtcl_0), 1, cs);
	if (ret)
		goto out;
	a6_cal_stage = 2;
	ret = a6_cal_packet(a6_n42_mtcl_1, sizeof(a6_n42_mtcl_1), 2, cs);
	if (!ret)
		a6_cal_stage = 3;
out:
	a6_cal_result = ret;
	pr_info("a6-touch-cal: stage=%u result=%d acks=%2phN,%2phN,%2phN\n",
		a6_cal_stage, ret, a6_cal_ack[0], a6_cal_ack[1], a6_cal_ack[2]);
	return ret;
}

static ssize_t a6_cal_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_TOUCH_N42_CAL_V1 stage=%u result=%d ack0=%2phN ack1=%2phN ack2=%2phN\n",
		a6_cal_stage, a6_cal_result, a6_cal_ack[0], a6_cal_ack[1],
		a6_cal_ack[2]);
	mutex_unlock(&a6_touch_lock);
	return n;
}
static struct kobj_attribute a6_cal_status_attr =
	__ATTR(status, 0400, a6_cal_status_show, NULL);
static struct attribute *a6_cal_attrs[] = {
	&a6_cal_status_attr.attr, NULL,
};
static const struct attribute_group a6_cal_group = {
	.name = "a6_touch_cal_n42", .attrs = a6_cal_attrs,
};
static int __init a6_cal_init(void)
{
	int ret;

	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_spi)
		return -ENODEV;
	ret = sysfs_create_group(firmware_kobj, &a6_cal_group);
	a6_cal_group_ready = !ret;
	return ret;
}
late_initcall(a6_cal_init);

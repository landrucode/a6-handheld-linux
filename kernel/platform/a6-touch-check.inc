// SPDX-License-Identifier: GPL-2.0-only
/* One n42 bootloader diagnostic, explicitly requested by root. No firmware. PMU rail pulse only in POWER_CHECK build.
 * Stock N1 vtable808684d4 +34c -> CHECK80855e64 (05 00 00 06 -> d0).
 * GPIO-CS build follows stock external function-spi_cs0; see chip-select audit.
 */
#include <linux/delay.h>

static bool a6_check_attempted, a6_check_restored;
#ifdef A6_TOUCH_GPIO_CS
static bool a6_gpio_cs_active;
static u32 a6_gpio_cs_idle, a6_gpio_cs_asserted, a6_gpio_cs_released;
#endif
static int a6_check_result;
static u32 a6_check_status, a6_check_atn_released;
static u32 a6_check_setup_status, a6_check_queued_status;
static u32 a6_check_control, a6_check_rx_remaining, a6_check_tx_remaining;
#if defined(A6_TOUCH_N1_VERSION) || defined(A6_TOUCH_N1_START_VERSION)
#define A6_CHECK_BYTES 8
static u32 a6_n1_version_value;
#ifdef A6_TOUCH_N1_START_VERSION
static u8 a6_n1_start_rx[2];
static unsigned int a6_n1_start_received;
#endif
#elif defined(A6_TOUCH_HBPP)
#define A6_CHECK_BYTES 16
/* N1 bootload entry uses slot520, not the inherited generic slot34c.
 * Stock8085dd20..ddc2 accepts each of the first two BE16 words below. */
static bool a6_hbpp_word_valid(unsigned int word)
{
	switch (word) {
	case 0x18e1: case 0x1aa1: case 0x1f01: case 0x4879:
	case 0x4969: case 0x4ad1: case 0x4bc1:
		return true;
	default:
		return false;
	}
}
#else
#define A6_CHECK_BYTES 4
#endif
static u8 a6_check_rx[A6_CHECK_BYTES];
static unsigned int a6_check_received;

static ssize_t a6_check_result_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
	#ifdef A6_TOUCH_N1_START_VERSION
		"A6_TOUCH_N1_START_VERSION_V1\n"
	#elif defined(A6_TOUCH_N1_VERSION)
		"A6_TOUCH_N1_VERSION_V1\n"
	#elif defined(A6_TOUCH_HBPP)
		"A6_TOUCH_HBPP_V1\n"
#elif defined(A6_TOUCH_GPIO_CS)
		"A6_TOUCH_POWER_GPIO_CS_V1\n"
#elif defined(A6_TOUCH_POWER_CHECK)
		"A6_TOUCH_POWER_CHECK_V1\n"
#elif defined(A6_TOUCH_PWM_CHECK)
		"A6_TOUCH_CHECK_PWM_V3\n"
#else
		"A6_TOUCH_CHECK_V2\n"
#endif
		"attempted=%u restored=%u result=%d received=%u rx=%*phN status=%08x atn_released=%08x divider=1024\n",
		a6_check_attempted, a6_check_restored, a6_check_result, a6_check_received,
		A6_CHECK_BYTES, a6_check_rx, a6_check_status, a6_check_atn_released);
	n += sysfs_emit_at(buf, n, "setup_status=%08x queued_status=%08x control=%08x rx_remaining=%u tx_remaining=%u\n",
		a6_check_setup_status, a6_check_queued_status, a6_check_control,
		a6_check_rx_remaining, a6_check_tx_remaining);
#if defined(A6_TOUCH_N1_VERSION) || defined(A6_TOUCH_N1_START_VERSION)
	n += sysfs_emit_at(buf, n, "controller_version=%08x expected=434d11a0\n",
		a6_n1_version_value);
#ifdef A6_TOUCH_N1_START_VERSION
	n += sysfs_emit_at(buf, n, "startup_received=%u startup_rx=%2phN startup_tx=19c1 startup_delay_ms=10\n",
		a6_n1_start_received, a6_n1_start_rx);
#endif
#endif
#ifdef A6_TOUCH_PWM_CHECK
	n += sysfs_emit_at(buf, n, "pwm_written=%u pwm_readback=%u pwm_restored=%u source_hz=%u high=%u low=%u\n",
		a6_pwm_probe_written, a6_pwm_probe_readback, a6_pwm_probe_restored,
		a6_pwm_probe_hz, a6_pwm_probe_high, a6_pwm_probe_low);
	n += sysfs_emit_at(buf, n, "pwm_first_10=%08x pwm_first_14=%08x pwm_first_20=%08x\npwm_later_10=%08x pwm_later_14=%08x pwm_later_20=%08x\n",
		a6_pwm_probe_first[0], a6_pwm_probe_first[1], a6_pwm_probe_first[2],
		a6_pwm_probe_later[0], a6_pwm_probe_later[1], a6_pwm_probe_later[2]);
#endif
#ifdef A6_TOUCH_POWER_CHECK
	n = a6_power_report(buf, n);
#ifdef A6_TOUCH_GPIO_CS
	n += sysfs_emit_at(buf, n, "gpio_cs_idle=%08x gpio_cs_asserted=%08x gpio_cs_released=%08x\n",
		a6_gpio_cs_idle, a6_gpio_cs_asserted, a6_gpio_cs_released);
#endif
#endif
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_check_run_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	#if defined(A6_TOUCH_N1_VERSION) || defined(A6_TOUCH_N1_START_VERSION)
	static const u8 command[] = { 0x1c, 0x73, 0x8f, 0xfc, 0x10, 0x00, 0x01, 0x9b };
	#elif defined(A6_TOUCH_HBPP)
	static const u8 command[] = {
		0x1a, 0xa1, 0x18, 0xe1, 0x18, 0xe1, 0x18, 0xe1,
		0x18, 0xe1, 0x18, 0xe1, 0x18, 0xe1, 0x18, 0xe1
	};
#else
	static const u8 command[] = { 5, 0, 0, 6 };
#endif
	/* Read-only snapshot of writable configuration, never RXDATA. */
	static const u32 offsets[] = { 0, 4, 0xc, 0x30, 0x34, 0x38, 0x4c };
	u32 saved[ARRAY_SIZE(offsets)], cs, reset, gate, status;
	unsigned int i, poll, available;
	int ret = 0;
	bool restored = true;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;

	#ifdef A6_TOUCH_N1_START_VERSION
	if (!sysfs_streq(buf, "start-read-n1-version"))
	#elif defined(A6_TOUCH_N1_VERSION)
	if (!sysfs_streq(buf, "read-n1-version"))
	#elif defined(A6_TOUCH_HBPP)
	if (!sysfs_streq(buf, "check-hbpp"))
#elif defined(A6_TOUCH_GPIO_CS)
	if (!sysfs_streq(buf, "check-with-gpio-cs"))
#elif defined(A6_TOUCH_POWER_CHECK)
	if (!sysfs_streq(buf, "check-with-power"))
#elif defined(A6_TOUCH_PWM_CHECK)
	if (!sysfs_streq(buf, "check-with-pwm"))
#else
	if (!sysfs_streq(buf, "check-bootloader"))
#endif
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (a6_check_attempted) {
		ret = -EALREADY;
		goto out;
	}
	gate = readl(a6_touch_pmgr + A6_TOUCH_GATE);
	if (gate == U32_MAX || (gate & 0xff) != 0xff ||
	    readl(a6_touch_pmgr + A6_TOUCH_GATE) != gate) {
		ret = -EBUSY;
		goto out;
	}
	cs = readl(a6_touch_gpio + A6_TOUCH_CS);
	reset = readl(a6_touch_gpio + A6_TOUCH_RESET);
	for (i = 0; i < ARRAY_SIZE(offsets); i++)
		saved[i] = readl(a6_touch_spi + offsets[i]);
	status = readl(a6_touch_spi + 8);
	/* Accept only the exact idle state measured on the observer boot.
	 * Never take over an active SPI engine or reinterpret a GPIO mode.
	 */
	if (cs != 0x202 || reset != 0x202 || status != 0 ||
	    saved[0] != 0 || saved[1] != 8 || saved[2] != 3 ||
	    saved[3] != 1 || saved[4] || saved[5] || saved[6]) {
		ret = -EBUSY;
		goto out;
	}
#ifdef A6_TOUCH_PWM_CHECK
	ret = a6_pwm_probe_validate();
	if (ret)
		goto out;
#endif
#ifdef A6_TOUCH_POWER_CHECK
	ret = a6_power_validate();
	if (ret) goto out;
#endif
	a6_check_attempted = true;
#ifdef A6_TOUCH_POWER_CHECK
	ret = a6_power_start();
	if (ret) goto restore;
#endif
#ifdef A6_TOUCH_PWM_CHECK
	ret = a6_pwm_probe_start();
	if (ret)
		goto restore;
	msleep(1);
#endif
	/* Stock GPIO mode14/15 changes only bit0 for these inherited modes. */
	writel(cs | 1, a6_touch_gpio + A6_TOUCH_CS);
#ifdef A6_TOUCH_GPIO_CS
	a6_gpio_cs_idle = readl(a6_touch_gpio + A6_TOUCH_CS);
	if (a6_gpio_cs_idle != 0x203) { ret = -EIO; goto restore; }
#endif
#ifndef A6_TOUCH_N1_START_VERSION
	writel(reset | 1, a6_touch_gpio + A6_TOUCH_RESET);
	msleep(20); /* stock personality reset-deassert-delay15, with margin */
	a6_check_atn_released = readl(a6_touch_gpio + A6_TOUCH_ATN);
#endif
	/* SPI version1: reset both FIFOs, configure 8-bit mode0, NCLK,
	 * PIO bit5; interrupt request bits7/8 and DMA bit6 remain clear.
	 * Divider is intentionally fixed; no unverified source-Hz claim.
	 */
	writel(0, a6_touch_spi);
	writel(1024, a6_touch_spi + 0x30);
	writel(0, a6_touch_spi + 0x38);
	writel(0x40000f, a6_touch_spi + 8);
	writel(0x4018, a6_touch_spi + 4);
#ifdef A6_TOUCH_N1_START_VERSION
	/* N1 slot528 is called while reset remains asserted.  It performs a
	 * distinct two-byte full-duplex 19c1 transaction, then delays 10ms.
	 * Stock deasserts reset only after this hook returns. */
	writel(2, a6_touch_spi + 0x34);
	writel(2, a6_touch_spi + 0x4c);
#else
	writel(A6_CHECK_BYTES, a6_touch_spi + 0x34);
	writel(A6_CHECK_BYTES, a6_touch_spi + 0x4c);
#endif
	/* Match stock807e059c ->807e0b94: RUN plus both FIFO resets,
	 * BEFORE selecting PIO and filling TX. The first experiment filled
	 * while stopped and timed out with no RX data.
	 */
	writel(0xd, a6_touch_spi);
#ifdef A6_TOUCH_GPIO_CS
	/* n42 has function-spi_cs0 and no internal-cs property. Stock3b0
	 * dispatches active1 through GPIO polarity0: physical level0. Keep
	 * controller PIN register inherited3; assert GPIO49 before any TX.
	 */
	a6_gpio_cs_active = true;
	writel(cs, a6_touch_gpio + A6_TOUCH_CS);
	a6_gpio_cs_asserted = readl(a6_touch_gpio + A6_TOUCH_CS);
	if (a6_gpio_cs_asserted != 0x202) { ret = -EIO; goto restore; }
#else
	writel(saved[2] & ~2, a6_touch_spi + 0xc);
#endif
	writel(0x4038, a6_touch_spi + 4);
	a6_check_setup_status = readl(a6_touch_spi + 8);
	udelay(10);
#ifdef A6_TOUCH_N1_START_VERSION
	writel(0x19, a6_touch_spi + 0x10);
	writel(0xc1, a6_touch_spi + 0x10);
	for (poll = 0; poll < 10000 && a6_n1_start_received < 2; poll++) {
		status = readl(a6_touch_spi + 8);
		available = (status >> 11) & 31;
		if (status == U32_MAX || available > 16) { ret = -EIO; goto restore; }
		while (available-- && a6_n1_start_received < 2)
			a6_n1_start_rx[a6_n1_start_received++] = readl(a6_touch_spi + 0x20);
		udelay(10);
	}
	if (a6_n1_start_received != 2) { ret = -ETIMEDOUT; goto restore; }
	/* End the startup transfer and release external CS before the stock
	 * hook's delay.  The version read below is a new wrapper transaction. */
	writel(0, a6_touch_spi);
	writel(cs | 1, a6_touch_gpio + A6_TOUCH_CS);
	a6_gpio_cs_active = false;
	msleep(10);
	writel(reset | 1, a6_touch_gpio + A6_TOUCH_RESET);
	msleep(20);
	a6_check_atn_released = readl(a6_touch_gpio + A6_TOUCH_ATN);
	writel(0x40000f, a6_touch_spi + 8);
	writel(0x4018, a6_touch_spi + 4);
	writel(A6_CHECK_BYTES, a6_touch_spi + 0x34);
	writel(A6_CHECK_BYTES, a6_touch_spi + 0x4c);
	writel(0xd, a6_touch_spi);
	a6_gpio_cs_active = true;
	writel(cs, a6_touch_gpio + A6_TOUCH_CS);
	if (readl(a6_touch_gpio + A6_TOUCH_CS) != 0x202) { ret = -EIO; goto restore; }
	writel(0x4038, a6_touch_spi + 4);
	udelay(10);
#endif
	for (i = 0; i < ARRAY_SIZE(command); i++)
		writel(command[i], a6_touch_spi + 0x10);
	a6_check_queued_status = readl(a6_touch_spi + 8);
	ret = -ETIMEDOUT;
	/* Fixed upper bound: 10000 polls, 10us delay, A6_CHECK_BYTES reads.
	 * The HBPP packet fits the proven version1 FIFO depth of16 exactly.
	 * No IRQ masking, DMA, retry, arbitrary payload or address interface.
	 */
	for (poll = 0; poll < 10000; poll++) {
		status = readl(a6_touch_spi + 8);
		a6_check_status = status;
		available = (status >> 11) & 31;
		if (status == U32_MAX || available > 16) {
			ret = -EIO;
			break;
		}
		while (available-- && a6_check_received < A6_CHECK_BYTES)
			a6_check_rx[a6_check_received++] = readl(a6_touch_spi + 0x20);
		if (a6_check_received == A6_CHECK_BYTES && !((status >> 6) & 31)) {
	#if defined(A6_TOUCH_N1_VERSION) || defined(A6_TOUCH_N1_START_VERSION)
			a6_n1_version_value = a6_check_rx[2] |
				(a6_check_rx[3] << 8) |
				(a6_check_rx[4] << 16) |
				(a6_check_rx[5] << 24);
			ret = a6_n1_version_value == 0x434d11a0 ? 0 : -EPROTO;
	#elif defined(A6_TOUCH_HBPP)
			ret = a6_hbpp_word_valid((a6_check_rx[0] << 8) | a6_check_rx[1]) &&
			      a6_hbpp_word_valid((a6_check_rx[2] << 8) | a6_check_rx[3]) ? 0 : -EPROTO;
#else
			ret = a6_check_rx[0] == 0xd0 ? 0 : -EPROTO;
#endif
			break;
		}
		udelay(10);
	}
	a6_check_control = readl(a6_touch_spi);
	a6_check_rx_remaining = readl(a6_touch_spi + 0x34);
	a6_check_tx_remaining = readl(a6_touch_spi + 0x4c);
	/* Every path after the first write comes here. Stop engine before
	 * deasserting CS, hold controller in original reset, flush and restore.
	 */
#ifdef A6_TOUCH_PWM_CHECK
restore:
#endif
	writel(0, a6_touch_spi);
#ifdef A6_TOUCH_GPIO_CS
	if (a6_gpio_cs_active) {
		writel(cs | 1, a6_touch_gpio + A6_TOUCH_CS);
		a6_gpio_cs_released = readl(a6_touch_gpio + A6_TOUCH_CS);
		if (a6_gpio_cs_released != 0x203) restored = false;
	}
#endif
	writel(saved[2], a6_touch_spi + 0xc);
	writel(reset, a6_touch_gpio + A6_TOUCH_RESET);
	writel(cs, a6_touch_gpio + A6_TOUCH_CS);
	writel(0xc, a6_touch_spi);
	writel(0, a6_touch_spi);
	writel(0x40000f, a6_touch_spi + 8);
	for (i = 1; i < ARRAY_SIZE(offsets); i++)
		writel(saved[i], a6_touch_spi + offsets[i]);
	writel(saved[0], a6_touch_spi);
	for (i = 0; i < ARRAY_SIZE(offsets); i++)
		if (readl(a6_touch_spi + offsets[i]) != saved[i])
			restored = false;
	if (readl(a6_touch_gpio + A6_TOUCH_CS) != cs ||
	    readl(a6_touch_gpio + A6_TOUCH_RESET) != reset)
		restored = false;
#ifdef A6_TOUCH_PWM_CHECK
	if (!a6_pwm_probe_restore())
		restored = false;
#endif
#ifdef A6_TOUCH_POWER_CHECK
	if (!a6_power_restore())
		restored = false;
#endif
	a6_check_restored = restored;
	if (!restored)
		ret = -EUCLEAN;
	a6_check_result = ret;
	pr_info("a6-touch: bounded touch diagnostic result=%d received=%u rx=%*phN restored=%u\n",
		ret, a6_check_received, A6_CHECK_BYTES, a6_check_rx, restored);
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_check_result_attr =
	__ATTR(result, 0400, a6_check_result_show, NULL);
static struct kobj_attribute a6_check_run_attr =
	__ATTR(run, 0200, NULL, a6_check_run_store);
static struct attribute *a6_check_attrs[] = {
	&a6_check_result_attr.attr, &a6_check_run_attr.attr, NULL,
};
static const struct attribute_group a6_check_group = {
	.name = "a6_touch_check", .attrs = a6_check_attrs,
};
static int __init a6_touch_check_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") ||
	    !a6_touch_spi || !a6_touch_gpio || !a6_touch_pmgr)
		return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_check_group);
}
late_initcall(a6_touch_check_init);

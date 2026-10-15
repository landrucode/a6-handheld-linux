// SPDX-License-Identifier: GPL-2.0-only
/* One fixed N42 Z2 packet in controller RAM. No NAND or arbitrary payload. */
#include <linux/jiffies.h>
#include <linux/sched.h>
#include <linux/ktime.h>

#define A6_FW_PACKET_BYTES 64340
#ifdef A6_TOUCH_POST_UPLOAD
static int a6_post_run(u32 cs);
#endif
#ifdef A6_TOUCH_REPORT_PROBE
static int a6_report_probe_run(u32 cs);
#endif
#ifdef A6_TOUCH_CALIBRATION
static int a6_cal_run(u32 cs);
#endif
#ifdef A6_TOUCH_NATIVE_INPUT
static bool a6_native_requested;
static int a6_native_start(u32 cs, u32 reset, const u32 *saved);
#endif
static bool a6_fw_attempted, a6_fw_restored;
static int a6_fw_result;
static unsigned int a6_fw_sent, a6_fw_probe_received, a6_fw_ack_received;
static u8 a6_fw_start_rx[2], a6_fw_probe_rx[16], a6_fw_ack_rx[2];
static u32 a6_fw_last_status, a6_fw_tx_remaining, a6_fw_rx_remaining;

#ifdef A6_TOUCH_NATIVE_INPUT
/* First eight transfers only; shared by bounded capture and worker. */
struct a6_touch_transfer_trace {
 u64 start_ns, end_ns;
 u32 atn_before, atn_after, cs_before, cs_after, reset_before, reset_after;
 unsigned int cpu_before, cpu_after, txlen, sent, received;
 u32 status, tx_remaining, rx_remaining;
 int result;
 u8 tx[16], rx[16];
};
static struct a6_touch_transfer_trace a6_touch_trace[8];
static struct a6_touch_transfer_trace a6_touch_last_transfer;
static unsigned int a6_touch_trace_count;
static bool a6_touch_trace_enabled;
static void a6_touch_trace_begin(void)
{
 memset(a6_touch_trace, 0, sizeof(a6_touch_trace));
 a6_touch_trace_count = 0;
 a6_touch_trace_enabled = true;
}
#endif

static int a6_fw_spi_xfer_mode(const u8 *tx, unsigned int txlen, u8 *rx,
		unsigned int rxlen, unsigned int timeout_ms, u32 cs, bool frame_pio)
{
	unsigned int sent = 0, received = 0, free_slots, available;
	unsigned long deadline = jiffies + msecs_to_jiffies(timeout_ms);
	u32 status, occupied;
	int ret = -ETIMEDOUT;
#ifdef A6_TOUCH_NATIVE_INPUT
 struct a6_touch_transfer_trace last = {0};
 struct a6_touch_transfer_trace *trace = NULL;
#endif

	if (!tx || !txlen || txlen > 0xffff || rxlen > txlen ||
#ifdef A6_TOUCH_REPORT_METADATA
	    rxlen > 838 ||
#else
	    rxlen > 16 ||
#endif
	    (rxlen && !rx) || cs != 0x202)
		return -EINVAL;
#ifdef A6_TOUCH_NATIVE_INPUT
 if (a6_touch_trace_enabled) {
  trace = &last;
  trace->start_ns = ktime_get_ns();
  trace->cpu_before = raw_smp_processor_id();
  trace->atn_before = readl(a6_touch_gpio + A6_TOUCH_ATN);
  trace->cs_before = readl(a6_touch_gpio + A6_TOUCH_CS);
  trace->reset_before = readl(a6_touch_gpio + A6_TOUCH_RESET);
  trace->txlen = txlen;
  memcpy(trace->tx, tx, min_t(unsigned int, txlen, 16));
 }
#endif
	writel(0, a6_touch_spi);
	writel(1024, a6_touch_spi + 0x30);
	writel(0, a6_touch_spi + 0x38);
	writel(0x40000f, a6_touch_spi + 8);
	writel(0x4018, a6_touch_spi + 4);
	writel(rxlen, a6_touch_spi + 0x34);
	writel(txlen, a6_touch_spi + 0x4c);
	writel(0xd, a6_touch_spi);
	writel(cs, a6_touch_gpio + A6_TOUCH_CS);
	if (readl(a6_touch_gpio + A6_TOUCH_CS) != cs) {
		ret = -EIO;
		goto stop;
	}
	writel(0x4038, a6_touch_spi + 4);
	udelay(10);
	for (;;) {
		status = readl(a6_touch_spi + 8);
		a6_fw_last_status = status;
		occupied = (status >> 6) & 31;
		available = (status >> 11) & 31;
		if (status == U32_MAX || occupied > 16 || available > 16 ||
		    available > rxlen - received) {
			ret = -EIO;
			break;
		}
		while (available--)
			rx[received++] = readl(a6_touch_spi + 0x20);
		free_slots = 16 - occupied;
		while (free_slots-- && sent < txlen)
			writel(tx[sent++], a6_touch_spi + 0x10);
		if (sent == txlen && received == rxlen &&
		    !((readl(a6_touch_spi + 8) >> 6) & 31) &&
		    !readl(a6_touch_spi + 0x4c) &&
		    !readl(a6_touch_spi + 0x34)) {
			ret = 0;
			break;
		}
		if (time_after(jiffies, deadline))
			break;
		/* Native frames must not pay a periodic-tick sleep for each FIFO
		 * refill. Keep IRQs/preemption enabled and the wall-time deadline. */
		if (frame_pio) udelay(5);
		else usleep_range(50, 100);
		cond_resched();
	}
stop:
	a6_fw_tx_remaining = readl(a6_touch_spi + 0x4c);
	a6_fw_rx_remaining = readl(a6_touch_spi + 0x34);
	writel(0, a6_touch_spi);
	writel(cs | 1, a6_touch_gpio + A6_TOUCH_CS);
	writel(0xc, a6_touch_spi);
	writel(0, a6_touch_spi);
	if (txlen == A6_FW_PACKET_BYTES)
		a6_fw_sent = sent;
	else if (txlen == 16)
		a6_fw_probe_received = received;
	else if (txlen == 2 && tx[0] == 0x1a && tx[1] == 0xa1)
		a6_fw_ack_received = received;
#ifdef A6_TOUCH_NATIVE_INPUT
 if (trace) {
  trace->end_ns = ktime_get_ns();
  trace->cpu_after = raw_smp_processor_id();
  trace->atn_after = readl(a6_touch_gpio + A6_TOUCH_ATN);
  trace->cs_after = readl(a6_touch_gpio + A6_TOUCH_CS);
  trace->reset_after = readl(a6_touch_gpio + A6_TOUCH_RESET);
  trace->sent = sent;
  trace->received = received;
  trace->status = a6_fw_last_status;
  trace->tx_remaining = a6_fw_tx_remaining;
  trace->rx_remaining = a6_fw_rx_remaining;
  trace->result = ret;
  if (received) memcpy(trace->rx, rx, min_t(unsigned int, received, 16));
  a6_touch_last_transfer = *trace;
  if (a6_touch_trace_count < ARRAY_SIZE(a6_touch_trace))
   a6_touch_trace[a6_touch_trace_count++] = *trace;
 }
#endif
	return ret;
}

static int a6_fw_spi_xfer(const u8 *tx, unsigned int txlen, u8 *rx,
		unsigned int rxlen, unsigned int timeout_ms, u32 cs)
{
	return a6_fw_spi_xfer_mode(tx, txlen, rx, rxlen, timeout_ms, cs, false);
}

#ifdef A6_TOUCH_NATIVE_INPUT
static int a6_native_spi_xfer(const u8 *tx, unsigned int txlen, u8 *rx,
		unsigned int rxlen, u32 cs)
{
	/* Fixed N42 negotiated maximum. 100 ms plus 10 ms per FIFO batch;
	 * at most 630 ms, including scheduling. No clock/divider changes. */
	if (!txlen || txlen > 838 || rxlen != txlen) return -EINVAL;
	return a6_fw_spi_xfer_mode(tx, txlen, rx, rxlen,
		100 + DIV_ROUND_UP(txlen, 16) * 10, cs, true);
}
#endif

static ssize_t a6_fw_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf,
		"A6_TOUCH_N42_FW_V1 attempted=%u result=%d restored=%u sent=%u/%u probe=%u ack=%u start_rx=%2phN probe_rx=%16phN ack_rx=%2phN status=%08x tx_remaining=%u rx_remaining=%u\n",
		a6_fw_attempted, a6_fw_result, a6_fw_restored, a6_fw_sent,
		A6_FW_PACKET_BYTES, a6_fw_probe_received, a6_fw_ack_received,
		a6_fw_start_rx, a6_fw_probe_rx, a6_fw_ack_rx,
		a6_fw_last_status, a6_fw_tx_remaining, a6_fw_rx_remaining);
	n = a6_power_report(buf, n);
	mutex_unlock(&a6_touch_lock);
	return n;
}

static ssize_t a6_fw_run_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	static const u8 start[] = {0x19, 0xc1};
	static const u8 probe[] = {
		0x1a, 0xa1, 0x18, 0xe1, 0x18, 0xe1, 0x18, 0xe1,
		0x18, 0xe1, 0x18, 0xe1, 0x18, 0xe1, 0x18, 0xe1,
	};
	static const u8 ack[] = {0x1a, 0xa1};
	static const u32 offsets[] = {0, 4, 0xc, 0x30, 0x34, 0x38, 0x4c};
	u32 saved[ARRAY_SIZE(offsets)], cs, reset, gate, status;
	unsigned int i;
	bool restored = true, powered = false, pwm_started = false;
	int ret;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
#ifdef A6_TOUCH_POST_UPLOAD
	if (!sysfs_streq(buf, "upload-and-calibrate-n42")
#ifdef A6_TOUCH_NATIVE_INPUT
	    && !sysfs_streq(buf, "start-native-n42")
#endif
	   )
#else
	if (!sysfs_streq(buf, "upload-fixed-n42"))
#endif
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
#ifdef A6_TOUCH_NATIVE_INPUT
	a6_native_requested = sysfs_streq(buf, "start-native-n42");
#endif
	if (a6_fw_attempted || a6_check_attempted) {
		ret = -EALREADY;
		goto out;
	}
	if (sizeof(a6_n42_fw_packet) != A6_FW_PACKET_BYTES ||
	    a6_n42_fw_packet[0] != 0x18 || a6_n42_fw_packet[1] != 0xe1) {
		ret = -EINVAL;
		goto out;
	}
	gate = readl(a6_touch_pmgr + A6_TOUCH_GATE);
	cs = readl(a6_touch_gpio + A6_TOUCH_CS);
	reset = readl(a6_touch_gpio + A6_TOUCH_RESET);
	status = readl(a6_touch_spi + 8);
	for (i = 0; i < ARRAY_SIZE(offsets); i++)
		saved[i] = readl(a6_touch_spi + offsets[i]);
	if (gate == U32_MAX || (gate & 0xff) != 0xff ||
	    readl(a6_touch_pmgr + A6_TOUCH_GATE) != gate ||
	    cs != 0x202 || reset != 0x202 || status ||
	    saved[0] || saved[1] != 8 || saved[2] != 3 ||
	    saved[3] != 1 || saved[4] || saved[5] || saved[6]) {
		ret = -EBUSY;
		goto out;
	}
	ret = a6_power_validate();
	if (ret)
		goto out;
	ret = a6_pwm_probe_validate();
	if (ret)
		goto out;
	a6_fw_attempted = true;
	powered = true;
	ret = a6_power_start();
	if (ret)
		goto restore;
	pwm_started = true;
	ret = a6_pwm_probe_start();
	if (ret)
		goto restore;
	writel(cs | 1, a6_touch_gpio + A6_TOUCH_CS);
	if (readl(a6_touch_gpio + A6_TOUCH_CS) != 0x203) {
		ret = -EIO;
		goto restore;
	}
	ret = a6_fw_spi_xfer(start, sizeof(start), a6_fw_start_rx,
			sizeof(a6_fw_start_rx), 1000, cs);
	if (ret)
		goto restore;
	msleep(10);
	writel(reset | 1, a6_touch_gpio + A6_TOUCH_RESET);
	msleep(20);
	ret = a6_fw_spi_xfer(probe, sizeof(probe), a6_fw_probe_rx,
			sizeof(a6_fw_probe_rx), 2000, cs);
	if (ret)
		goto restore;
	if (!a6_hbpp_word_valid((a6_fw_probe_rx[0] << 8) | a6_fw_probe_rx[1]) ||
	    !a6_hbpp_word_valid((a6_fw_probe_rx[2] << 8) | a6_fw_probe_rx[3])) {
		ret = -EPROTO;
		goto restore;
	}
#ifdef A6_TOUCH_CALIBRATION
	ret = a6_cal_run(cs);
	if (ret)
		goto restore;
#endif
	ret = a6_fw_spi_xfer(a6_n42_fw_packet, A6_FW_PACKET_BYTES,
			NULL, 0, 90000, cs);
	if (ret)
		goto restore;
	ret = a6_fw_spi_xfer(ack, sizeof(ack), a6_fw_ack_rx,
			sizeof(a6_fw_ack_rx), 2000, cs);
	if (!ret && ((a6_fw_ack_rx[0] << 8) | a6_fw_ack_rx[1]) != 0x4bc1)
		ret = -EPROTO;
#ifdef A6_TOUCH_POST_UPLOAD
	if (!ret)
		ret = a6_post_run(cs);
#endif
#ifdef A6_TOUCH_REPORT_PROBE
	if (!ret)
		ret = a6_report_probe_run(cs);
#endif
#ifdef A6_TOUCH_NATIVE_INPUT
	if (!ret && a6_native_requested) {
		ret = a6_native_start(cs, reset, saved);
		if (!ret) {
			a6_fw_result = 0;
			pr_info("a6-touch-native: input registered; controller retained\n");
			goto out;
		}
	}
#endif
restore:
	writel(0, a6_touch_spi);
	writel(cs | 1, a6_touch_gpio + A6_TOUCH_CS);
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
	if (pwm_started && !a6_pwm_probe_restore())
		restored = false;
	if (powered && !a6_power_restore())
		restored = false;
	a6_fw_restored = restored;
	if (!restored)
		ret = -EUCLEAN;
	a6_fw_result = ret;
	pr_info("a6-touch-fw: result=%d sent=%u ack=%2phN restored=%u\n",
		ret, a6_fw_sent, a6_fw_ack_rx, restored);
out:
	mutex_unlock(&a6_touch_lock);
	return ret ? ret : count;
}

static struct kobj_attribute a6_fw_status_attr =
	__ATTR(status, 0400, a6_fw_status_show, NULL);
static struct kobj_attribute a6_fw_run_attr =
	__ATTR(run, 0200, NULL, a6_fw_run_store);
static struct attribute *a6_fw_attrs[] = {
	&a6_fw_status_attr.attr, &a6_fw_run_attr.attr, NULL,
};
static const struct attribute_group a6_fw_group = {
	.name = "a6_touch_fw_n42", .attrs = a6_fw_attrs,
};
static int __init a6_fw_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_spi ||
	    !a6_touch_gpio || !a6_touch_pmgr || !a6_touch_i2c || !a6_touch_pwm)
		return -ENODEV;
	return sysfs_create_group(firmware_kobj, &a6_fw_group);
}
late_initcall(a6_fw_init);

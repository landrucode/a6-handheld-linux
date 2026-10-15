// SPDX-License-Identifier: GPL-2.0-only
/* N42 live-validated Z2 framing, polled type-B input; no guessed IRQ routing. */
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/workqueue.h>
#include <linux/unaligned.h>
#include <linux/reboot.h>

static struct input_dev *a6_native_input;
static struct workqueue_struct *a6_native_queue;
static struct delayed_work a6_native_work;
static bool a6_native_active;
static bool a6_native_identity_attempted;
static int a6_native_identity_result;
static u8 a6_native_identity_rx[2][16];
static u8 a6_native_sequence = 1;
static unsigned int a6_native_poll_cpu, a6_native_reply_cpu, a6_native_first_cpu, a6_native_first_reply_cpu;
static u32 a6_native_cs, a6_native_reset, a6_native_saved[7];
static const u32 a6_native_offsets[] = {0, 4, 0xc, 0x30, 0x34, 0x38, 0x4c};
static u8 a6_native_tx[838], a6_native_rx[838];
static unsigned int a6_native_frames, a6_native_errors, a6_native_streak;
static unsigned int a6_native_invalid_lengths, a6_native_empty_lengths;
static unsigned int a6_native_coordinate_clamps;
static unsigned int a6_native_warmup_streak;
static unsigned int a6_native_setup_polls, a6_native_setup_frames;
static unsigned int a6_native_width, a6_native_height;
static int a6_native_result;
static u8 a6_native_length_reply[16], a6_native_first_reply[16], a6_native_first_wire[838];
static unsigned int a6_native_stage, a6_native_first_stage, a6_native_wire_bytes;
static unsigned int a6_native_first_bytes, a6_native_idle_polls, a6_native_atn;
static int a6_native_first_result;
static bool a6_native_first_failure;
static struct a6_touch_transfer_trace a6_native_first_transfer, a6_native_error_transfer;
static int a6_native_reject(int error)
{
	if (!a6_native_first_failure) {
		a6_native_first_failure = true;
		a6_native_first_result = error;
		a6_native_first_stage = a6_native_stage;
		a6_native_first_cpu = a6_native_poll_cpu;
		a6_native_first_reply_cpu = a6_native_reply_cpu;
		a6_native_first_transfer = a6_touch_last_transfer;
		memcpy(a6_native_first_reply, a6_native_length_reply, 16);
		a6_native_first_bytes = a6_native_wire_bytes;
		memcpy(a6_native_first_wire, a6_native_rx, a6_native_first_bytes);
	}
	a6_native_error_transfer = a6_touch_last_transfer;
	return error;
}


/* Caller holds the transport/PMU mutex. Never hold it while cancelling work. */
static void a6_native_restore(void)
{
	unsigned int i;
	bool restored = true;
	writel(0, a6_touch_spi);
	writel(a6_native_cs | 1, a6_touch_gpio + A6_TOUCH_CS);
	writel(a6_native_reset, a6_touch_gpio + A6_TOUCH_RESET);
	writel(a6_native_cs, a6_touch_gpio + A6_TOUCH_CS);
	writel(0xc, a6_touch_spi);
	writel(0, a6_touch_spi);
	writel(0x40000f, a6_touch_spi + 8);
	for (i = 1; i < ARRAY_SIZE(a6_native_offsets); i++)
		writel(a6_native_saved[i], a6_touch_spi + a6_native_offsets[i]);
	writel(a6_native_saved[0], a6_touch_spi);
	for (i = 0; i < ARRAY_SIZE(a6_native_offsets); i++)
		if (readl(a6_touch_spi + a6_native_offsets[i]) != a6_native_saved[i]) restored = false;
	if (readl(a6_touch_gpio + A6_TOUCH_CS) != a6_native_cs ||
	    readl(a6_touch_gpio + A6_TOUCH_RESET) != a6_native_reset) restored = false;
	if (!a6_pwm_probe_restore()) restored = false;
	if (!a6_power_restore()) restored = false;
	a6_fw_restored = restored;
	if (!restored) a6_native_result = -EUCLEAN;
}

static int a6_native_poll(void)
{
	u8 reply[16], *p, *r;
	unsigned int length, wire, payload, header, count, stride, i, j;
	u16 sum;
	int ret, slot;
	a6_native_poll_cpu = raw_smp_processor_id();
	a6_native_reply_cpu = a6_native_poll_cpu;
	a6_native_stage = 0;
	a6_native_wire_bytes = 0;
	a6_native_atn = readl(a6_touch_gpio + A6_TOUCH_ATN);
	/* Live successful transfers started with ATN low and returned high.
	 * Treat high as idle; this polarity remains a hardware candidate. */
	if (a6_native_atn & 1) { a6_native_idle_polls++; return 0; }
	memset(a6_native_tx, 0, sizeof(a6_native_tx));
	a6_native_tx[0] = 0xeb;
	a6_native_tx[1] = a6_native_sequence;
	a6_report_checksum(a6_native_tx);
	ret = a6_native_spi_xfer(a6_native_tx, 16, reply, 16, a6_native_cs);
	if (ret) return a6_native_reject(ret);
	a6_native_reply_cpu = raw_smp_processor_id();
	memcpy(a6_native_length_reply, reply, 16);
	a6_native_stage = 1;
	if ((reply[0] & 0xf0) != 0xe0 || !a6_report_reply_valid(reply, reply[0])) {
		a6_native_invalid_lengths++;
		/* The controller can expose a short E2/E1 turnaround window after
		 * metadata setup. Let the next scheduled poll observe it. */
		return a6_native_reject(-EAGAIN);
	}
	length = get_unaligned_le16(reply + 1);
	if (!length) { a6_native_empty_lengths++; return 0; }
	if (length < 26 || length > a6_report_max_packet - 5 || length > 833) return a6_native_reject(-EMSGSIZE);
	a6_native_stage = 2;
	wire = length + 5;
	memset(a6_native_tx, 0, sizeof(a6_native_tx));
	a6_native_tx[0] = 0xeb;
	a6_native_tx[1] = a6_native_sequence;
	a6_native_tx[2] = 1;
	sum = 0xeb + a6_native_sequence + 1;
	put_unaligned_le16(sum, a6_native_tx + wire - 2);
	ret = a6_native_spi_xfer(a6_native_tx, wire, a6_native_rx, wire, a6_native_cs);
	if (ret) return a6_native_reject(ret);
	a6_native_wire_bytes = wire;
	a6_native_stage = 3;
	if ((a6_native_rx[0] != 0xea && a6_native_rx[0] != 0xeb) ||
	    a6_native_rx[1] != a6_native_sequence || get_unaligned_le16(a6_native_rx + 2) != length) return a6_native_reject(-EPROTO);
	sum = 0;
	for (i = 0; i < 5; i++) sum += a6_native_rx[i];
	if ((u8)sum) return a6_native_reject(-EPROTO);
	a6_native_stage = 4;
	sum = 0;
	for (i = 5; i < wire - 2; i++) sum += a6_native_rx[i];
	if (get_unaligned_le16(a6_native_rx + wire - 2) != sum) return a6_native_reject(-EPROTO);
	a6_native_sequence = a6_native_sequence == 1 ? 2 : 1;
	a6_native_stage = 5;
	p = a6_native_rx + 5;
	payload = length - 2;
	header = p[2]; count = p[16]; stride = p[17];
	if ((p[0] != 0x43 && p[0] != 0x44) || header < 24 || header > payload ||
	    count > 10 || (count && (stride < 30 || count > (payload - header) / stride))) return a6_native_reject(-EPROTO);
	/* Validate the whole frame before publishing any event. */
	for (i = 0; i < count; i++) {
		r = p + header + i * stride;
		for (j = 0; j < i; j++) if (r[0] == p[header + j * stride]) return a6_native_reject(-EPROTO);
	}
	for (i = 0; i < count; i++) {
		int x, y;
		r = p + header + i * stride;
		slot = input_mt_get_slot_by_key(a6_native_input, r[0]);
		if (slot < 0) continue;
		input_mt_slot(a6_native_input, slot);
		if (!input_mt_report_slot_state(a6_native_input, MT_TOOL_FINGER, r[1] == 3 || r[1] == 4)) continue;
		/* Z2 contact positions are signed 16-bit values. Live N42 packets
		 * include small negative edge coordinates; clamp to advertised
		 * screen bounds rather than treating them as transport failures. */
		x = (s16)get_unaligned_le16(r + 4);
		y = (s16)get_unaligned_le16(r + 6);
		if (x < 0 || x > (int)a6_native_width) a6_native_coordinate_clamps++;
		if (y < 0 || y > (int)a6_native_height) a6_native_coordinate_clamps++;
		input_report_abs(a6_native_input, ABS_MT_POSITION_X,
			clamp_t(int, x, 0, a6_native_width));
		input_report_abs(a6_native_input, ABS_MT_POSITION_Y,
			clamp_t(int, y, 0, a6_native_height));
	}
	input_mt_sync_frame(a6_native_input);
	input_sync(a6_native_input);
	a6_native_frames++;
	return 0;
}

static void a6_native_worker(struct work_struct *work)
{
	int ret;
	mutex_lock(&a6_touch_lock);
	if (!a6_native_active) goto out;
	/* Same first EB request/sequence and periodic cadence as the bounded
	 * capture. The low-attention gate is checked by the polling helper. */
	ret = a6_native_poll();
	if (ret == -EAGAIN) {
		/* A finite diagnostic grace period, not unlimited fault masking. */
		if (++a6_native_warmup_streak >= 64) ret = -EPROTO;
	} else a6_native_warmup_streak = 0;
	if (ret && ret != -EAGAIN) {
		a6_native_errors++;
		a6_native_streak++;
	} else if (!ret) a6_native_streak = 0;
	if (a6_native_streak >= 8) {
		a6_native_result = ret;
		a6_native_active = false;
		input_mt_sync_frame(a6_native_input);
		input_sync(a6_native_input);
		a6_native_restore();
		pr_err("a6-touch-native: stopped after repeated errors %d\n", ret);
	} else queue_delayed_work_on(0, a6_native_queue, &a6_native_work, msecs_to_jiffies(20));
out:
	mutex_unlock(&a6_touch_lock);
}

static int a6_native_start(u32 cs, u32 reset, const u32 *saved)
{
	int ret;
	unsigned long deadline;
	if (a6_report_meta_result[4] || a6_report_meta_length[4] < 8) return -EPROTO;
	a6_native_width = get_unaligned_le32(a6_report_metadata[4] + 3);
	a6_native_height = get_unaligned_le32(a6_report_metadata[4] + 7);
	if (a6_native_width != 5000 || a6_native_height != 8900) return -ENODEV;
	a6_native_input = input_allocate_device();
	if (!a6_native_input) return -ENOMEM;
	a6_native_input->name = "A6 N42 native touchscreen";
	a6_native_input->phys = "a6/spi1/input0";
	a6_native_input->id.bustype = BUS_SPI;
	input_set_abs_params(a6_native_input, ABS_MT_POSITION_X, 0, a6_native_width, 0, 0);
	input_set_abs_params(a6_native_input, ABS_MT_POSITION_Y, 0, a6_native_height, 0, 0);
	ret = input_mt_init_slots(a6_native_input, 10, INPUT_MT_DIRECT | INPUT_MT_DROP_UNUSED);
	if (ret) goto free;
	a6_native_queue = alloc_workqueue("a6-touch-native", WQ_MEM_RECLAIM, 1);
	if (!a6_native_queue) { ret = -ENOMEM; goto free; }
	ret = input_register_device(a6_native_input);
	if (ret) { destroy_workqueue(a6_native_queue); goto free; }
	a6_native_cs = cs; a6_native_reset = reset;
	memcpy(a6_native_saved, saved, sizeof(a6_native_saved));
	a6_touch_trace_begin();
	a6_native_active = true;
	/* Match the successful capture's setup-caller context before the
	 * asynchronous handoff. Caller already holds a6_touch_lock. */
	deadline = jiffies + msecs_to_jiffies(20000);
	while (time_before(jiffies, deadline) && a6_native_setup_polls < 1000) {
		ret = a6_native_poll();
		a6_native_setup_polls++;
		/* Malformed replies are retained/counted during this finite window.
		 * Abort on transport failure; do not publish rejected contacts. */
		if (ret == -ETIMEDOUT || ret == -EIO) break;
		msleep(20);
	}
	a6_native_setup_frames = a6_native_frames;
	if (ret == -ETIMEDOUT || ret == -EIO) {
		a6_native_result = ret;
		a6_native_active = false;
		a6_native_restore();
		input_unregister_device(a6_native_input);
		a6_native_input = NULL;
		destroy_workqueue(a6_native_queue);
		a6_native_queue = NULL;
		return ret;
	}
	INIT_DELAYED_WORK(&a6_native_work, a6_native_worker);
	queue_delayed_work_on(0, a6_native_queue, &a6_native_work, msecs_to_jiffies(20));
	return 0;
free:
	input_free_device(a6_native_input);
	a6_native_input = NULL;
	return ret;
}

static ssize_t a6_native_status_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	unsigned int i;
	mutex_lock(&a6_touch_lock);
	n = sysfs_emit(buf, "A6_NATIVE_INPUT_V1 active=%u result=%d frames=%u errors=%u streak=%u width=%u height=%u restored=%u\n",
		a6_native_active, a6_native_result, a6_native_frames, a6_native_errors,
		a6_native_streak, a6_native_width, a6_native_height, a6_fw_restored);
	n += sysfs_emit_at(buf, n, "identity_attempted=%u identity_result=%d identity_first=%16phN identity_second=%16phN\n", a6_native_identity_attempted, a6_native_identity_result, a6_native_identity_rx[0], a6_native_identity_rx[1]);
	n += sysfs_emit_at(buf, n, "invalid_lengths=%u empty_lengths=%u warmup_streak=%u warmup_limit=64\n", a6_native_invalid_lengths, a6_native_empty_lengths, a6_native_warmup_streak);
	n += sysfs_emit_at(buf, n, "coordinate_clamps=%u\n", a6_native_coordinate_clamps);
	n += sysfs_emit_at(buf, n, "setup_polls=%u setup_frames=%u setup_window_ms=20000\n", a6_native_setup_polls, a6_native_setup_frames);
	n += sysfs_emit_at(buf, n, "poll_cpu=%u reply_cpu=%u first_cpu=%u first_reply_cpu=%u atn=%08x idle_polls=%u first_failure=%u first_stage=%u first_result=%d first_bytes=%u\nfirst_length_reply=",
		a6_native_poll_cpu, a6_native_reply_cpu, a6_native_first_cpu, a6_native_first_reply_cpu,
		a6_native_atn, a6_native_idle_polls, a6_native_first_failure,
		a6_native_first_stage, a6_native_first_result, a6_native_first_bytes);
	for (i = 0; i < 16; i++) n += sysfs_emit_at(buf, n, "%02x", a6_native_first_reply[i]);
	n += sysfs_emit_at(buf, n,
		"\nfirst_spi_txlen=%u sent=%u received=%u status=%08x tx_remaining=%u rx_remaining=%u duration_ns=%llu\n"
		"last_error_spi_txlen=%u sent=%u received=%u status=%08x tx_remaining=%u rx_remaining=%u duration_ns=%llu\nfirst_wire=",
		a6_native_first_transfer.txlen, a6_native_first_transfer.sent,
		a6_native_first_transfer.received, a6_native_first_transfer.status,
		a6_native_first_transfer.tx_remaining, a6_native_first_transfer.rx_remaining,
		(unsigned long long)(a6_native_first_transfer.end_ns - a6_native_first_transfer.start_ns),
		a6_native_error_transfer.txlen, a6_native_error_transfer.sent,
		a6_native_error_transfer.received, a6_native_error_transfer.status,
		a6_native_error_transfer.tx_remaining, a6_native_error_transfer.rx_remaining,
		(unsigned long long)(a6_native_error_transfer.end_ns - a6_native_error_transfer.start_ns));
	for (i = 0; i < a6_native_first_bytes; i++) n += sysfs_emit_at(buf, n, "%02x", a6_native_first_wire[i]);
	n += sysfs_emit_at(buf, n, "\n");
	mutex_unlock(&a6_touch_lock);
	return n;
}
static ssize_t a6_native_trace_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
 ssize_t n;
 unsigned int i;
 if (!capable(CAP_SYS_RAWIO)) return -EPERM;
 mutex_lock(&a6_touch_lock);
 n = sysfs_emit(buf, "A6_TOUCH_TRANSFER_TRACE_V1 count=%u\n", a6_touch_trace_count);
 for (i = 0; i < a6_touch_trace_count; i++) {
  struct a6_touch_transfer_trace *t = &a6_touch_trace[i];
  n += sysfs_emit_at(buf, n, "i=%u start_ns=%llu end_ns=%llu cpu=%u/%u atn=%08x/%08x cs=%08x/%08x reset=%08x/%08x txlen=%u received=%u result=%d tx=%16phN rx=%16phN\n",
   i, (unsigned long long)t->start_ns, (unsigned long long)t->end_ns,
   t->cpu_before, t->cpu_after, t->atn_before, t->atn_after, t->cs_before, t->cs_after,
   t->reset_before, t->reset_after, t->txlen, t->received, t->result, t->tx, t->rx);
 }
 mutex_unlock(&a6_touch_lock);
 return n;
}
static struct kobj_attribute a6_native_trace_attr = __ATTR(transfers, 0400, a6_native_trace_show, NULL);
static DEFINE_MUTEX(a6_native_control_lock);
static int a6_native_stop(void)
{
	int ret = 0;
	mutex_lock(&a6_native_control_lock);
	mutex_lock(&a6_touch_lock);
	if (!a6_native_input) goto out;
	a6_native_active = false;
	mutex_unlock(&a6_touch_lock);
	cancel_delayed_work_sync(&a6_native_work);
	mutex_lock(&a6_touch_lock);
	if (!a6_fw_restored) a6_native_restore();
	input_unregister_device(a6_native_input);
	a6_native_input = NULL;
	destroy_workqueue(a6_native_queue);
	a6_native_queue = NULL;
	ret = a6_native_result;
out:
	mutex_unlock(&a6_touch_lock);
	mutex_unlock(&a6_native_control_lock);
	return ret;
}
static ssize_t a6_native_stop_store(struct kobject *kobj, struct kobj_attribute *attr,
		const char *buf, size_t count)
{
	int ret;
	if (!capable(CAP_SYS_RAWIO)) return -EPERM;
	if (!sysfs_streq(buf, "stop")) return -EINVAL;
	ret = a6_native_stop();
	return ret ? ret : count;
}
static int a6_native_shutdown(struct sys_off_data *data)
{
	/* Sleepable prepare phase, before the charger/PMU shutdown sequence. */
	a6_native_stop();
	return NOTIFY_DONE;
}
static struct kobj_attribute a6_native_stop_attr = __ATTR(control, 0200, NULL, a6_native_stop_store);
static struct kobj_attribute a6_native_status_attr = __ATTR(status, 0400, a6_native_status_show, NULL);
static struct attribute *a6_native_attrs[] = { &a6_native_status_attr.attr, &a6_native_stop_attr.attr, &a6_native_trace_attr.attr, NULL };
static const struct attribute_group a6_native_group = { .name = "a6_touch_native", .attrs = a6_native_attrs };
static int __init a6_native_init(void)
{
	struct sys_off_handler *off, *restart;
	int ret;
	off = register_sys_off_handler(SYS_OFF_MODE_POWER_OFF_PREPARE,
		SYS_OFF_PRIO_HIGH, a6_native_shutdown, NULL);
	if (IS_ERR(off)) return PTR_ERR(off);
	restart = register_sys_off_handler(SYS_OFF_MODE_RESTART_PREPARE,
		SYS_OFF_PRIO_HIGH, a6_native_shutdown, NULL);
	if (IS_ERR(restart)) { unregister_sys_off_handler(off); return PTR_ERR(restart); }
	ret = sysfs_create_group(firmware_kobj, &a6_native_group);
	if (ret) { unregister_sys_off_handler(restart); unregister_sys_off_handler(off); }
	return ret;
}
late_initcall(a6_native_init);

// SPDX-License-Identifier: GPL-2.0-only
/* Bounded n42 BQ27540 HDQ read using the waveform recovered from the matching
 * iOS 10.3.4 AppleHDQGasGaugeControl and AppleD1972PMU kexts. The sole PMU
 * byte write asserts the stock battery_swi request around one transaction;
 * the exact inherited byte is restored on every exit. No charger writes.
 */
#include <linux/capability.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/kobject.h>
#include <linux/mutex.h>
#include <linux/sysfs.h>

#define A6_HDQ_UART_BASE 0x32a00000
#define A6_HDQ_PMGR_BASE 0x3f101000
#define A6_HDQ_UART_GATE 0x10c
#define A6_HDQ_GPIO_BASE 0x3fa00000
#define A6_HDQ_GPIO44    0x0b0
#define A6_HDQ_UCON      0x04
#define A6_HDQ_UFCON     0x08
#define A6_HDQ_UTRSTAT   0x10
#define A6_HDQ_UERSTAT   0x14
#define A6_HDQ_UFSTAT    0x18
#define A6_HDQ_UTXH      0x20
#define A6_HDQ_URXH      0x24
#define A6_HDQ_UBRDIV    0x28
#define A6_HDQ_UDIVSLOT  0x2c
#define A6_HDQ_SBREAK    BIT(4)
#define A6_HDQ_RXRESET   BIT(1)
#define A6_HDQ_TXRESET   BIT(2)
#define A6_HDQ_TXFULL    BIT(9)
#define A6_HDQ_RXFULL    BIT(8)
#define A6_HDQ_RXMASK    0x0f
#define A6_HDQ_TXEMPTY   BIT(2)
#define A6_HDQ_RAW_MAX   24
#define A6_HDQ_I2C_BASE  0x33200000
#define A6_HDQ_I2C_GATE  0x118
#define A6_HDQ_PMU_REG   0x6d
#define A6_HDQ_I2C_XIP   BIT(28)
#define A6_HDQ_I2C_XEN   BIT(27)
#define A6_HDQ_I2C_RX    BIT(19)
#define A6_HDQ_I2C_TX    BIT(16)
#define A6_HDQ_I2C_ERR   (BIT(25)|BIT(24)|BIT(23)|BIT(22)|BIT(21)|BIT(6))
#define A6_HDQ_PMU_MAX   8

static void __iomem *a6_hdq_uart, *a6_hdq_pmgr, *a6_hdq_gpio, *a6_hdq_i2c;
static DEFINE_MUTEX(a6_hdq_lock);
#ifdef A6_HDQ_WITH_VBAT_MONITOR
/* The touch/D1972 diagnostic below defines this mutex with its initializer. */
static struct mutex a6_touch_lock;
#endif
static bool a6_hdq_attempted, a6_hdq_restored;
static int a6_hdq_result;
static u32 a6_hdq_saved[6], a6_hdq_final[6];
static u8 a6_hdq_raw[3][A6_HDQ_RAW_MAX], a6_hdq_count[3], a6_hdq_value[3];
static u32 a6_hdq_errors[3];
static u32 a6_hdq_stage, a6_hdq_last_utrstat, a6_hdq_last_ufstat;
static u32 a6_hdq_tx_utrstat[6], a6_hdq_tx_ufstat[6];
static u32 a6_hdq_break_error, a6_hdq_rx_ufstat[6];
static int a6_hdq_rx_reset_result;
static u32 a6_hdq_rx_reset_ufcon;
static int a6_hdq_preflush_tx_result, a6_hdq_preflush_rx_result;
static u32 a6_hdq_preflush_utrstat, a6_hdq_preflush_error,
	   a6_hdq_preflush_ufcon;
static u32 a6_hdq_programmed_ubrdiv, a6_hdq_programmed_udivslot;
#ifdef A6_HDQ_TX_TURNAROUND
static u32 a6_hdq_tx_disabled, a6_hdq_tx_reenabled;
#endif
static u8 a6_hdq_pmu_bank, a6_hdq_pmu_saved, a6_hdq_pmu_asserted,
	  a6_hdq_pmu_final;
static bool a6_hdq_pmu_saved_valid, a6_hdq_pmu_maybe_written,
	   a6_hdq_pmu_restored, a6_hdq_i2c_idle;
static unsigned int a6_hdq_pmu_transactions, a6_hdq_pmu_polls;
static u32 a6_hdq_pmu_status[A6_HDQ_PMU_MAX];
#ifdef A6_HDQ_LINE_OBSERVER
#define A6_HDQ_LINE_SAMPLES 128
static u32 a6_hdq_line_before, a6_hdq_line_requested, a6_hdq_line_after;
static u32 a6_hdq_line_first, a6_hdq_line_last, a6_hdq_line_changes;
static u32 a6_hdq_line_bits[A6_HDQ_LINE_SAMPLES / 32];
#endif
#ifdef A6_HDQ_PHASE_OBSERVER
#define A6_HDQ_PHASE_SAMPLES 128
struct a6_hdq_phase_trace {
	u32 first, last, changes, count, elapsed_us;
	u32 bits[A6_HDQ_PHASE_SAMPLES / 32];
};
static struct a6_hdq_phase_trace a6_hdq_phase[4];

#ifdef A6_HDQ_REALTIME_US
static int a6_hdq_wait_until(u64 deadline)
{
	unsigned int spin;

	for (spin = 0; spin < 1000000; spin++) {
		if (ktime_get_ns() >= deadline)
			return 0;
		cpu_relax();
	}
	return -ETIMEDOUT;
}

static int a6_hdq_wait_us(unsigned int duration)
{
	return a6_hdq_wait_until(ktime_get_ns() + (u64)duration * 1000);
}
#endif

static int a6_hdq_capture_phase(unsigned int phase, unsigned int samples)
{
	struct a6_hdq_phase_trace *trace = &a6_hdq_phase[phase];
	u64 start = ktime_get_ns();
	u32 previous = 0;
	unsigned int i;
	int ret = 0;

	for (i = 0; i < samples; i++) {
		u32 pin;

	#ifdef A6_HDQ_REALTIME_US
		ret = a6_hdq_wait_until(start + (u64)i * 10000);
		if (ret)
			break;
	#endif
		pin = readl(a6_hdq_gpio + A6_HDQ_GPIO44);

		if (!i)
			trace->first = pin;
		else if ((pin ^ previous) & 1)
			trace->changes++;
		if (pin & 1)
			trace->bits[i / 32] |= BIT(i % 32);
		previous = pin;
	#ifndef A6_HDQ_REALTIME_US
		udelay(10);
	#endif
	}
	#ifdef A6_HDQ_REALTIME_US
	if (!ret)
		ret = a6_hdq_wait_until(start + (u64)samples * 10000);
	#endif
	trace->last = previous;
	trace->count = i;
	trace->elapsed_us = div_u64(ktime_get_ns() - start, 1000);
	return ret;
}
#endif

static const u32 a6_hdq_cfg_offsets[] = { 0, 4, 8, 0xc, 0x28, 0x2c };

static bool a6_hdq_i2c_is_idle(u32 state)
{
	return state != U32_MAX &&
		!(state & (A6_HDQ_I2C_XIP | A6_HDQ_I2C_ERR | A6_HDQ_I2C_RX)) &&
		(state & A6_HDQ_I2C_TX);
}

static int a6_hdq_pmu_byte(u8 reg, u8 *value, bool write)
{
	u32 state, data, needed = A6_HDQ_I2C_XEN | A6_HDQ_I2C_TX;
	unsigned int poll, slot;

	if (a6_hdq_pmu_transactions >= A6_HDQ_PMU_MAX)
		return -EOVERFLOW;
	state = readl(a6_hdq_i2c + 0x14);
	if (!a6_hdq_i2c_is_idle(state))
		return -EBUSY;
	slot = a6_hdq_pmu_transactions++;
	writel(state, a6_hdq_i2c + 0x14);
	writel(0x1e8, a6_hdq_i2c);
	if (write) {
		/* D1972 address 0x74: one pointer byte and data byte with STOP. */
		writel(reg, a6_hdq_i2c);
		writel(0x200 | *value, a6_hdq_i2c);
	} else {
		writel(0x200 | reg, a6_hdq_i2c);
		writel(0x1e9, a6_hdq_i2c);
		writel(0x601, a6_hdq_i2c);
		needed |= A6_HDQ_I2C_RX;
	}
	for (poll = 0; poll < 10000; poll++) {
		state = readl(a6_hdq_i2c + 0x14);
		a6_hdq_pmu_status[slot] = state;
		a6_hdq_pmu_polls++;
		if (state == U32_MAX)
			return -EIO;
		if (state & A6_HDQ_I2C_ERR)
			return (state & BIT(21)) ? -ENXIO : -EIO;
		if (!(state & A6_HDQ_I2C_XIP) &&
		    (state & needed) == needed)
			break;
		udelay(10);
	}
	if (poll == 10000)
		return -ETIMEDOUT;
	if (!write) {
		data = readl(a6_hdq_i2c + 4);
		if (data & ~0xffU)
			return -ENODATA;
		*value = data;
	} else if (state & A6_HDQ_I2C_RX) {
		return -EIO;
	}
	writel(A6_HDQ_I2C_XEN, a6_hdq_i2c + 0x14);
	return 0;
}

static void a6_hdq_i2c_recover(void)
{
	u32 state = readl(a6_hdq_i2c + 0x14);
	if (!a6_hdq_i2c_is_idle(state)) {
		writel(0x704, a6_hdq_i2c + 0x1c);
		udelay(10);
		writel(0x104, a6_hdq_i2c + 0x1c);
		state = readl(a6_hdq_i2c + 0x14);
	}
	if (state != U32_MAX)
		writel(state, a6_hdq_i2c + 0x14);
}

static void a6_hdq_pmu_restore(void)
{
	int ret;

	if (!a6_hdq_pmu_saved_valid || !a6_hdq_pmu_maybe_written)
		return;
	a6_hdq_i2c_recover();
	ret = a6_hdq_pmu_byte(A6_HDQ_PMU_REG, &a6_hdq_pmu_saved, true);
	if (!ret)
		ret = a6_hdq_pmu_byte(A6_HDQ_PMU_REG, &a6_hdq_pmu_final, false);
	a6_hdq_pmu_restored = !ret &&
		a6_hdq_pmu_final == a6_hdq_pmu_saved;
	a6_hdq_i2c_recover();
	a6_hdq_i2c_idle = a6_hdq_i2c_is_idle(readl(a6_hdq_i2c + 0x14));
}

static int a6_hdq_rx_fifo_reset(void)
{
	u32 ufcon = readl(a6_hdq_uart + A6_HDQ_UFCON);
 	u32 state;

	/* RESETRX is self-clearing.  Do not race the controller by explicitly
	 * deasserting it: the Samsung UART driver uses the same single write for
	 * a live FIFO flush.
	 */
	writel(ufcon | A6_HDQ_RXRESET, a6_hdq_uart + A6_HDQ_UFCON);
	return readl_poll_timeout_atomic(a6_hdq_uart + A6_HDQ_UFCON, state,
		!(state & A6_HDQ_RXRESET), 1, 100);
}

static int a6_hdq_tx_fifo_reset(void)
{
	u32 ufcon = readl(a6_hdq_uart + A6_HDQ_UFCON);
	u32 state;

	writel(ufcon | A6_HDQ_TXRESET, a6_hdq_uart + A6_HDQ_UFCON);
	return readl_poll_timeout_atomic(a6_hdq_uart + A6_HDQ_UFCON, state,
		!(state & A6_HDQ_TXRESET), 1, 100);
}

static int a6_hdq_apple_preflush(void)
{
	/* AppleHDQ issues TXQ_FLUSH (0x28), then RXQ_FLUSH (0x2f), before
	 * BREAK. AppleSamsungSerial's RX helper writes UTRSTAT 0x60, reads
	 * UERSTAT, and performs the self-clearing UFCON RX reset in that order.
	 */
	a6_hdq_preflush_tx_result = a6_hdq_tx_fifo_reset();
	if (a6_hdq_preflush_tx_result)
		return a6_hdq_preflush_tx_result;
	writel(0x60, a6_hdq_uart + A6_HDQ_UTRSTAT);
	a6_hdq_preflush_utrstat = readl(a6_hdq_uart + A6_HDQ_UTRSTAT);
	a6_hdq_preflush_error = readl(a6_hdq_uart + A6_HDQ_UERSTAT);
	a6_hdq_preflush_rx_result = a6_hdq_rx_fifo_reset();
	a6_hdq_preflush_ufcon = readl(a6_hdq_uart + A6_HDQ_UFCON);
	return a6_hdq_preflush_rx_result;
}

static int a6_hdq_read_byte(u8 command, unsigned int slot)
{
	#ifndef A6_HDQ_TX_TURNAROUND
	static const unsigned int tx_wait_us[] = { 1000, 2000, 7000, 20000, 70000 };
	#endif
	static const unsigned int rx_wait_us[] = { 250, 500, 1000, 2000, 3000 };
	u32 state, ucon, count = 0;
	u8 encoded[8];
	unsigned int i;
	int ret;

	/* Apple encodes each HDQ bit as one 57600-baud UART character. */
	for (i = 0; i < 8; i++)
		encoded[i] = command & BIT(i) ? 0xfe : 0xc0;

	ret = a6_hdq_apple_preflush();
	if (ret)
		return ret;
	ucon = readl(a6_hdq_uart + A6_HDQ_UCON);
	writel(ucon | A6_HDQ_SBREAK, a6_hdq_uart + A6_HDQ_UCON);
#ifdef A6_HDQ_PHASE_OBSERVER
	if (!slot) {
		ret = a6_hdq_capture_phase(0, 20);
	} else {
	#ifdef A6_HDQ_REALTIME_US
		ret = a6_hdq_wait_us(200);
	#else
		udelay(200);
	#endif
	}
#else
	udelay(200);
#endif
	writel(ucon, a6_hdq_uart + A6_HDQ_UCON);
	if (ret)
		return ret;
#ifdef A6_HDQ_PHASE_OBSERVER
	if (!slot) {
		ret = a6_hdq_capture_phase(1, 4);
	} else {
	#ifdef A6_HDQ_REALTIME_US
		ret = a6_hdq_wait_us(40);
	#else
		udelay(40);
	#endif
	}
#else
	udelay(40);
#endif
	if (ret)
		return ret;
	/* BREAK is received locally as a framed zero. Let that character finish,
	 * then discard it and clear its expected BREAK/FRAME status before data.
	 */
	#ifdef A6_HDQ_REALTIME_US
	ret = a6_hdq_wait_us(200);
	if (ret)
		return ret;
	#else
	udelay(200);
	#endif
	a6_hdq_rx_reset_result = a6_hdq_rx_fifo_reset();
	a6_hdq_rx_reset_ufcon = readl(a6_hdq_uart + A6_HDQ_UFCON);
	if (a6_hdq_rx_reset_result)
		return a6_hdq_rx_reset_result;
	a6_hdq_break_error = readl(a6_hdq_uart + A6_HDQ_UERSTAT);

	for (i = 0; i < 8; i++) {
		a6_hdq_stage = 10 + i;
		ret = readl_poll_timeout_atomic(a6_hdq_uart + A6_HDQ_UFSTAT,
			state, !(state & A6_HDQ_TXFULL), 2, 2000);
		a6_hdq_last_ufstat = state;
		if (ret)
			return ret;
		/* Apple S5L ports are UPIO_MEM32, including their data register. */
		writel(encoded[i], a6_hdq_uart + A6_HDQ_UTXH);
	}
#ifdef A6_HDQ_PHASE_OBSERVER
	#ifndef A6_HDQ_TX_TURNAROUND
	if (!slot) {
		ret = a6_hdq_capture_phase(2, A6_HDQ_PHASE_SAMPLES);
		if (ret)
			return ret;
	}
	#endif
#elif defined(A6_HDQ_LINE_OBSERVER)
	if (!slot) {
		u32 previous = 0;
		for (i = 0; i < A6_HDQ_LINE_SAMPLES; i++) {
			u32 pin = readl(a6_hdq_gpio + A6_HDQ_GPIO44);
			if (!i)
				a6_hdq_line_first = pin;
			else if ((pin ^ previous) & 1)
				a6_hdq_line_changes++;
			if (pin & 1)
				a6_hdq_line_bits[i / 32] |= BIT(i % 32);
			previous = pin;
			udelay(10);
		}
		a6_hdq_line_last = previous;
	}
#endif
	/* The boot firmware leaves a divisor but not a documented source rate.
	 * Record bounded progress rather than assuming the nominal character time.
	 */
	#ifdef A6_HDQ_TX_TURNAROUND
	{
		u64 deadline = ktime_get_ns() + 5000000;
		/* Poll immediately after queueing the final symbol. A delayed
		 * phase capture could miss the gauge's sub-ms reply window.
		 */
		for (i = 0; i < 1000000; i++) {
			state = readl(a6_hdq_uart + A6_HDQ_UTRSTAT);
			if (state & A6_HDQ_TXEMPTY || ktime_get_ns() >= deadline)
				break;
			cpu_relax();
		}
		a6_hdq_stage = 20;
		a6_hdq_tx_utrstat[0] = state;
		a6_hdq_tx_ufstat[0] = readl(a6_hdq_uart + A6_HDQ_UFSTAT);
		a6_hdq_last_utrstat = state;
		a6_hdq_last_ufstat = a6_hdq_tx_ufstat[0];
	}
	#else
	for (i = 0; i < ARRAY_SIZE(a6_hdq_tx_utrstat); i++) {
		a6_hdq_stage = 20 + i;
		a6_hdq_tx_utrstat[i] = readl(a6_hdq_uart + A6_HDQ_UTRSTAT);
		a6_hdq_tx_ufstat[i] = readl(a6_hdq_uart + A6_HDQ_UFSTAT);
		a6_hdq_last_utrstat = a6_hdq_tx_utrstat[i];
		a6_hdq_last_ufstat = a6_hdq_tx_ufstat[i];
		if (a6_hdq_tx_utrstat[i] & A6_HDQ_TXEMPTY)
			break;
		if (i < ARRAY_SIZE(tx_wait_us))
			usleep_range(tx_wait_us[i], tx_wait_us[i] + 100);
	}
	#endif
	if (!(a6_hdq_last_utrstat & A6_HDQ_TXEMPTY))
		return -ETIMEDOUT;
#ifdef A6_HDQ_TX_TURNAROUND
	/* The gauge shares the TX wire. Test whether leaving UART TX enabled
	 * prevents its open-drain reply. RX remains enabled throughout. Only the
	 * exact observed UCON baseline is accepted; restore before any RX verdict.
	 */
	if (ucon != 0x405)
		return -EPROTO;
	writel(ucon & ~0xcU, a6_hdq_uart + A6_HDQ_UCON);
	a6_hdq_tx_disabled = readl(a6_hdq_uart + A6_HDQ_UCON);
	if (a6_hdq_tx_disabled != 0x401) {
		writel(ucon, a6_hdq_uart + A6_HDQ_UCON);
		return -EIO;
	}
#endif
#ifdef A6_HDQ_PHASE_OBSERVER
	if (!slot) {
		ret = a6_hdq_capture_phase(3, A6_HDQ_PHASE_SAMPLES);
	#ifdef A6_HDQ_TX_TURNAROUND
		if (ret)
			goto reenable_tx;
	#else
		if (ret)
			return ret;
	#endif
	}
#endif

	/* A full transaction can contain eight echo and eight response symbols.
	 * Observe bounded RX progress instead of assuming a fixed response delay.
	 */
	for (i = 0; i < ARRAY_SIZE(a6_hdq_rx_ufstat); i++) {
		state = readl(a6_hdq_uart + A6_HDQ_UFSTAT);
		a6_hdq_rx_ufstat[i] = state;
		if (state & A6_HDQ_RXFULL)
			break;
		if (i < ARRAY_SIZE(rx_wait_us))
			usleep_range(rx_wait_us[i], rx_wait_us[i] + 100);
	}
	state = readl(a6_hdq_uart + A6_HDQ_UFSTAT);
	a6_hdq_stage = 30;
	a6_hdq_last_ufstat = state;
	count = state & A6_HDQ_RXMASK;
	if (state & A6_HDQ_RXFULL)
		count = 16;
	#ifdef A6_HDQ_TX_TURNAROUND
	/* Finish the bounded RX window before restoring TX. The echo remains in
	 * FIFO even if the gauge did not answer; read it after TX is restored.
	 */
reenable_tx:
	writel(ucon, a6_hdq_uart + A6_HDQ_UCON);
	a6_hdq_tx_reenabled = readl(a6_hdq_uart + A6_HDQ_UCON);
	if (a6_hdq_tx_reenabled != ucon)
		return -EUCLEAN;
	if (ret)
		return ret;
	#endif
	if (count < 8 || count > 16)
		return -EPROTO;
	a6_hdq_count[slot] = count;
	a6_hdq_errors[slot] = readl(a6_hdq_uart + A6_HDQ_UERSTAT);
	for (i = 0; i < count; i++)
		a6_hdq_raw[slot][i] = readl(a6_hdq_uart + A6_HDQ_URXH);
	if (a6_hdq_errors[slot])
		return -EIO;
	/* UART5 receives its own eight command symbols. A lone echo is not a
	 * gauge response, even though it is a full byte of HDQ symbols.
	 */
	for (i = 0; i < 8; i++)
		if (a6_hdq_raw[slot][i] != encoded[i])
			return -EPROTO;
	if (count != 16)
		return -ENODATA;
	for (i = 8; i < 16; i++)
		if (a6_hdq_raw[slot][i] > 0xf8)
			a6_hdq_value[slot] |= BIT(i - 8);
	return 0;
}

static void a6_hdq_restore(void)
{
	unsigned int i;

	/* Release BREAK and discard any symbols left by a timed-out transfer. */
	writel(a6_hdq_saved[1], a6_hdq_uart + A6_HDQ_UCON);
	writel(readl(a6_hdq_uart + A6_HDQ_UFCON) | A6_HDQ_TXRESET,
	       a6_hdq_uart + A6_HDQ_UFCON);
	/* Restore the complete inherited configuration. */
	for (i = 0; i < ARRAY_SIZE(a6_hdq_cfg_offsets); i++)
		writel(a6_hdq_saved[i], a6_hdq_uart + a6_hdq_cfg_offsets[i]);
	for (i = 0; i < ARRAY_SIZE(a6_hdq_cfg_offsets); i++)
		a6_hdq_final[i] = readl(a6_hdq_uart + a6_hdq_cfg_offsets[i]);
	a6_hdq_restored = !memcmp(a6_hdq_saved, a6_hdq_final,
				  sizeof(a6_hdq_saved));
}

static ssize_t a6_hdq_status_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	u16 voltage = a6_hdq_value[0] | (a6_hdq_value[1] << 8);
	ssize_t n;
	unsigned int slot;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	mutex_lock(&a6_hdq_lock);
	n = sysfs_emit(buf,
#ifdef A6_HDQ_PHASE_OBSERVER
	#ifdef A6_HDQ_TX_TURNAROUND
		"A6_BATTERY_HDQ_TX_TURNAROUND_V5\n"
	#elif defined(A6_HDQ_ECHO_GUARD)
		"A6_BATTERY_HDQ_ECHO_GUARD_V4\n"
	#elif defined(A6_HDQ_REALTIME_US)
		"A6_BATTERY_HDQ_TIMED_V3\n"
	#else
		"A6_BATTERY_HDQ_PHASE_V2\n"
	#endif
#elif defined(A6_HDQ_LINE_OBSERVER)
		"A6_BATTERY_HDQ_LINE_V1\n"
#else
		"A6_BATTERY_HDQ_READ_V9\n"
#endif
		"attempted=%u restored=%u result=%d voltage_mv=%u soc_percent=%u plausible=%u\n"
		"stage=%u last_utrstat=%08x last_ufstat=%08x break_error=%08x rx_reset=%d rx_reset_ufcon=%08x\n"
		"preflush_tx=%d preflush_rx=%d preflush_utrstat=%08x preflush_error=%08x preflush_ufcon=%08x\n"
		"programmed_ubrdiv=%08x programmed_udivslot=%08x\n"
		"pmu_bank=%02x pmu_saved=%02x pmu_asserted=%02x pmu_final=%02x pmu_restored=%u i2c_idle=%u pmu_transactions=%u pmu_polls=%u\n"
		"saved=%08x,%08x,%08x,%08x,%08x,%08x\n"
		"final=%08x,%08x,%08x,%08x,%08x,%08x\n",
		a6_hdq_attempted, a6_hdq_restored, a6_hdq_result,
		voltage, a6_hdq_value[2],
		voltage >= 2500 && voltage <= 4500 && a6_hdq_value[2] <= 100,
		a6_hdq_stage, a6_hdq_last_utrstat, a6_hdq_last_ufstat,
		a6_hdq_break_error, a6_hdq_rx_reset_result,
		a6_hdq_rx_reset_ufcon,
		a6_hdq_preflush_tx_result, a6_hdq_preflush_rx_result,
		a6_hdq_preflush_utrstat, a6_hdq_preflush_error,
		a6_hdq_preflush_ufcon,
		a6_hdq_programmed_ubrdiv, a6_hdq_programmed_udivslot,
		a6_hdq_pmu_bank, a6_hdq_pmu_saved, a6_hdq_pmu_asserted,
		a6_hdq_pmu_final, a6_hdq_pmu_restored, a6_hdq_i2c_idle,
		a6_hdq_pmu_transactions, a6_hdq_pmu_polls,
		a6_hdq_saved[0], a6_hdq_saved[1], a6_hdq_saved[2],
		a6_hdq_saved[3], a6_hdq_saved[4], a6_hdq_saved[5],
		a6_hdq_final[0], a6_hdq_final[1], a6_hdq_final[2],
		a6_hdq_final[3], a6_hdq_final[4], a6_hdq_final[5]);
#ifdef A6_HDQ_TX_TURNAROUND
	n += sysfs_emit_at(buf, n, "tx_disabled=%08x tx_reenabled=%08x\n",
		a6_hdq_tx_disabled, a6_hdq_tx_reenabled);
#endif
#ifdef A6_HDQ_LINE_OBSERVER
	n += sysfs_emit_at(buf, n,
		"line_gpio_before=%08x requested=%08x after=%08x first=%08x last=%08x changes=%u bit0_bitmap=%08x,%08x,%08x,%08x\n",
		a6_hdq_line_before, a6_hdq_line_requested,
		a6_hdq_line_after, a6_hdq_line_first, a6_hdq_line_last,
		a6_hdq_line_changes, a6_hdq_line_bits[0],
		a6_hdq_line_bits[1], a6_hdq_line_bits[2], a6_hdq_line_bits[3]);
#endif
#ifdef A6_HDQ_PHASE_OBSERVER
	for (slot = 0; slot < ARRAY_SIZE(a6_hdq_phase); slot++) {
		const struct a6_hdq_phase_trace *trace = &a6_hdq_phase[slot];

		n += sysfs_emit_at(buf, n,
			"phase%u count=%u elapsed_us=%u first=%08x last=%08x changes=%u bit0_bitmap=%08x,%08x,%08x,%08x\n",
			slot, trace->count, trace->elapsed_us, trace->first,
			trace->last, trace->changes, trace->bits[0],
			trace->bits[1], trace->bits[2], trace->bits[3]);
	}
#endif
	for (slot = 0; slot < ARRAY_SIZE(a6_hdq_tx_utrstat); slot++)
		n += sysfs_emit_at(buf, n, "tx%u utrstat=%08x ufstat=%08x\n",
			slot, a6_hdq_tx_utrstat[slot], a6_hdq_tx_ufstat[slot]);
	for (slot = 0; slot < ARRAY_SIZE(a6_hdq_rx_ufstat); slot++)
		n += sysfs_emit_at(buf, n, "rx%u ufstat=%08x\n",
			slot, a6_hdq_rx_ufstat[slot]);
	for (slot = 0; slot < 3; slot++)
		n += sysfs_emit_at(buf, n,
			"read%u command=%02x count=%u value=%02x error=%08x raw=%*phN\n",
			slot, (u8[]){ 0x88, 0x89, 0xac }[slot],
			a6_hdq_count[slot], a6_hdq_value[slot],
			a6_hdq_errors[slot], a6_hdq_count[slot], a6_hdq_raw[slot]);
	mutex_unlock(&a6_hdq_lock);
	return n;
}

static ssize_t a6_hdq_run_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	static const u8 commands[] = { 0x88, 0x89, 0xac };
	u32 gate, gpio, i2c_gate;
	unsigned int i;
	int ret = 0;

	if (!capable(CAP_SYS_RAWIO))
		return -EPERM;
	if (!sysfs_streq(buf, "read-basic-once"))
		return -EINVAL;
#ifdef A6_HDQ_WITH_VBAT_MONITOR
	mutex_lock(&a6_touch_lock);
#endif
	mutex_lock(&a6_hdq_lock);
	if (a6_hdq_attempted) {
		ret = -EALREADY;
		goto out;
	}
	a6_hdq_attempted = true;
	gate = readl(a6_hdq_pmgr + A6_HDQ_UART_GATE);
	i2c_gate = readl(a6_hdq_pmgr + A6_HDQ_I2C_GATE);
	gpio = readl(a6_hdq_gpio + A6_HDQ_GPIO44);
#ifdef A6_HDQ_LINE_OBSERVER
	a6_hdq_line_before = gpio;
#endif
	for (i = 0; i < ARRAY_SIZE(a6_hdq_cfg_offsets); i++)
		a6_hdq_saved[i] = readl(a6_hdq_uart + a6_hdq_cfg_offsets[i]);
	if ((gate & 0xff) != 0xff || i2c_gate != 0x2ff ||
	    i2c_gate != readl(a6_hdq_pmgr + A6_HDQ_I2C_GATE) ||
	    gpio != 0x241 || readl(a6_hdq_gpio + 0xe8) != 0x221 ||
	    readl(a6_hdq_gpio + 0xec) != 0x221 ||
	    readl(a6_hdq_i2c + 0x28) != 1 ||
	    readl(a6_hdq_i2c + 0x1c) != 0x104 ||
	    readl(a6_hdq_i2c + 0x18) != 0 ||
	    !a6_hdq_i2c_is_idle(readl(a6_hdq_i2c + 0x14)) ||
	    a6_hdq_saved[0] != 7 || a6_hdq_saved[1] != 0x405 ||
	    a6_hdq_saved[2] != 1 || a6_hdq_saved[3] != 1 ||
	    a6_hdq_saved[4] != 0x19 || a6_hdq_saved[5] != 0) {
		ret = -EBUSY;
		goto restore;
	}
	ret = a6_hdq_pmu_byte(0x1e, &a6_hdq_pmu_bank, false);
	if (ret || a6_hdq_pmu_bank != 0) {
		if (!ret)
			ret = -EPROTO;
		goto restore;
	}
	ret = a6_hdq_pmu_byte(A6_HDQ_PMU_REG, &a6_hdq_pmu_saved, false);
	if (ret)
		goto restore;
	a6_hdq_pmu_saved_valid = true;
	/* AppleD1972PMU's index-5 GPIO function applies config fd/18 and then
	 * request bit 02. Derive the requested byte exactly as that code does,
	 * but accept it only when the evidenced result is 1a. Preserve the actual
	 * inherited byte (da on V7) for exact restoration rather than emulating
	 * Apple's release-to-18 operation.
	 */
	a6_hdq_pmu_asserted = (a6_hdq_pmu_saved & (u8)~0xfd) | 0x18 | 0x02;
	if (a6_hdq_pmu_asserted != 0x1a) {
		ret = -EPROTO;
		goto restore;
	}
	a6_hdq_pmu_maybe_written = true;
	ret = a6_hdq_pmu_byte(A6_HDQ_PMU_REG, &a6_hdq_pmu_asserted, true);
	if (ret)
		goto restore;
	ret = a6_hdq_pmu_byte(A6_HDQ_PMU_REG, &a6_hdq_pmu_asserted, false);
	if (ret || a6_hdq_pmu_asserted != 0x1a) {
		if (!ret)
			ret = -EIO;
		goto restore;
	}
#ifdef A6_HDQ_LINE_OBSERVER
	a6_hdq_line_requested = readl(a6_hdq_gpio + A6_HDQ_GPIO44);
#endif
	/* Apple's matching driver requests 115200 half-bits/s: 57600 baud.
	 * Firmware left this 48 MHz UART at divisor 0x19 (about 115200 baud).
	 * Use the exact integer divisor for 57600 and restore it on every exit.
	 */
	writel(0x33, a6_hdq_uart + A6_HDQ_UBRDIV);
	writel(0, a6_hdq_uart + A6_HDQ_UDIVSLOT);
	a6_hdq_programmed_ubrdiv = readl(a6_hdq_uart + A6_HDQ_UBRDIV);
	a6_hdq_programmed_udivslot = readl(a6_hdq_uart + A6_HDQ_UDIVSLOT);
	if (a6_hdq_programmed_ubrdiv != 0x33 || a6_hdq_programmed_udivslot) {
		ret = -EIO;
		goto restore;
	}
	for (i = 0; i < ARRAY_SIZE(commands); i++) {
		ret = a6_hdq_read_byte(commands[i], i);
		if (ret)
			break;
	#ifdef A6_HDQ_REALTIME_US
		ret = a6_hdq_wait_us(200);
		if (ret)
			break;
	#else
		udelay(200);
	#endif
	}
	if (!ret) {
		u16 voltage = a6_hdq_value[0] | (a6_hdq_value[1] << 8);

		if (voltage < 2500 || voltage > 4500 || a6_hdq_value[2] > 100)
			ret = -ERANGE;
	}
restore:
	a6_hdq_pmu_restore();
	a6_hdq_restore();
#ifdef A6_HDQ_LINE_OBSERVER
	a6_hdq_line_after = readl(a6_hdq_gpio + A6_HDQ_GPIO44);
#endif
	if ((!a6_hdq_restored ||
	     (a6_hdq_pmu_maybe_written &&
	      (!a6_hdq_pmu_restored || !a6_hdq_i2c_idle))) && !ret)
		ret = -EUCLEAN;
	a6_hdq_result = ret;
	pr_info("a6-battery: HDQ basic read result=%d restored=%u voltage=%u soc=%u\n",
		ret, a6_hdq_restored,
		a6_hdq_value[0] | (a6_hdq_value[1] << 8), a6_hdq_value[2]);
out:
	mutex_unlock(&a6_hdq_lock);
#ifdef A6_HDQ_WITH_VBAT_MONITOR
	mutex_unlock(&a6_touch_lock);
#endif
	return ret ? ret : count;
}

static struct kobj_attribute a6_hdq_status_attr =
	__ATTR(status, 0400, a6_hdq_status_show, NULL);
static struct kobj_attribute a6_hdq_run_attr =
	__ATTR(run, 0200, NULL, a6_hdq_run_store);
static struct attribute *a6_hdq_attrs[] = {
	&a6_hdq_status_attr.attr, &a6_hdq_run_attr.attr, NULL,
};
static const struct attribute_group a6_hdq_group = {
	.name = "a6_battery_hdq", .attrs = a6_hdq_attrs,
};

static int __init a6_hdq_init(void)
{
	if (!of_machine_is_compatible("apple,n42ap"))
		return -ENODEV;
	a6_hdq_uart = ioremap(A6_HDQ_UART_BASE, 0x1000);
	a6_hdq_pmgr = ioremap(A6_HDQ_PMGR_BASE, 0x1000);
	a6_hdq_gpio = ioremap(A6_HDQ_GPIO_BASE, 0x1000);
	a6_hdq_i2c = ioremap(A6_HDQ_I2C_BASE, 0x1000);
	if (!a6_hdq_uart || !a6_hdq_pmgr || !a6_hdq_gpio || !a6_hdq_i2c)
		return -ENOMEM;
	return sysfs_create_group(firmware_kobj, &a6_hdq_group);
}
late_initcall(a6_hdq_init);

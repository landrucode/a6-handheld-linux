// SPDX-License-Identifier: GPL-2.0-only
/* Fixed n42 rail pulse around the existing PWM/CHECK. Caller holds touch lock.
 * Only PMU22 eb<->ef and23 ad<->ed. No bank, voltage or GPIO68 writes.
 * Every possibly submitted write is tracked before TX and restored even
 * after NACK/timeout: failure does not prove the peripheral ignored data.
 */
#define A6_TOUCH_POWER_CHECK 1
#define A6_POWER_XIP (1U<<28)
#define A6_POWER_XEN (1U<<27)
#define A6_POWER_RX (1U<<19)
#define A6_POWER_TX (1U<<16)
#define A6_POWER_ERR ((1U<<25)|(1U<<24)|(1U<<23)|(1U<<22)|(1U<<21)|(1U<<6))
#ifdef A6_CHARGER_PROOF
/* The charger proof performs 10 baseline reads, 3 writes, 4 active reads,
 * 11 samples, 3 restore writes and 5 final reads: 36 logged operations.
 */
#define A6_POWER_MAX 48
#else
#define A6_POWER_MAX 24
#endif
static unsigned int a6_power_transactions, a6_power_polls;
static u32 a6_power_status[A6_POWER_MAX];
static u8 a6_power_regs[A6_POWER_MAX], a6_power_values[A6_POWER_MAX];
static bool a6_power_writes[A6_POWER_MAX];
static u8 a6_power_before[6], a6_power_enabled[2], a6_power_after[5];
static bool a6_power_saved, a6_power_maybe_ana, a6_power_maybe_ldo;
static bool a6_power_idle, a6_power_config_ok, a6_power_restored;
static int a6_power_start_result, a6_power_cleanup_result;

static bool a6_power_is_idle(u32 s)
{
	/* XEN is a completion event and may be clear after its W1C acknowledge. */
	return s != U32_MAX && !(s & (A6_POWER_XIP|A6_POWER_ERR|A6_POWER_RX)) &&
		(s & A6_POWER_TX);
}
static int a6_power_validate(void)
{
	if (!a6_touch_i2c) return -ENODEV;
	if (readl(a6_touch_pmgr+A6_TOUCH_I2C_GATE) != 0x2ff ||
	    readl(a6_touch_pmgr+A6_TOUCH_I2C_GATE) != 0x2ff ||
	    readl(a6_touch_gpio+0xe8) != 0x221 || readl(a6_touch_gpio+0xec) != 0x221 ||
	    readl(a6_touch_i2c+0x28) != 1 || readl(a6_touch_i2c+0x1c) != 0x104 ||
	    readl(a6_touch_i2c+0x18) ||
	    (readl(a6_touch_i2c+0x14) != 0x08010100 &&
	     readl(a6_touch_i2c+0x14) != 0x00010100))
		return -EBUSY;
	return 0;
}
#ifdef A6_D1972_POLICY
/* Stock shutdown reads only; keep the write allowlist unchanged. */
static bool a6_power_shutdown_read_reg(u8 reg)
{
	return (reg >= 0x68 && reg <= 0x73) || reg == 0xb0 || reg == 0xb9;
}
#endif
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
static bool a6_power_stock_off_reg(u8 reg, bool write)
{
	if (write)
		return reg == 0x7d || reg == 0x62 || reg == 0xa2 ||
		       reg == 0xa4 || reg == 0xb0;
	return (reg >= 0x01 && reg <= 0x09) || reg == 0xa4;
}
#endif
static int a6_power_xfer(u8 reg, u8 *value, bool write, bool log)
{
	/* Preflight accepts acknowledged XEN=0, but every newly submitted
	 * transaction must raise XEN before its inherited TX-empty bit counts.
	 */
	u32 s, d, needed = A6_POWER_XEN|A6_POWER_TX;
	unsigned int i, slot = 0;
	/* Persistent input limit and one-shot ADC use no finite proof slots. */
	if (!log && !(!write && reg == 0x43)
#ifdef A6_D1972_VBUS_ADC
	    && !(reg >= 0x48 && reg <= 0x4a && (!write || reg == 0x48))
#endif
#ifdef A6_D1972_POLICY
	    && !(reg == 0x1b || reg == 0x3f || reg == 0x43 ||
	         (!write && (reg == 0x45 || reg == 0x46 ||
	                     a6_power_shutdown_read_reg(reg))))
#endif
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
	    && !a6_power_stock_off_reg(reg, write)
#endif
	    ) return -EINVAL;
	if (write) {
		if (!(
#ifdef A6_D1972_VBUS_ADC
		    (!log && reg == 0x48) ||
#endif
		    (a6_power_saved && ((reg == 0x22 && (*value == 0xeb || *value == 0xef)) ||
		    (reg == 0x23 && (*value == 0xad || *value == 0xed))))
#ifdef A6_CHARGER_PROOF
		    || reg == 0x1b || reg == 0x3f || reg == 0x43
#endif
#ifdef A6_D1972_POLICY
		    || (!log && (reg == 0x1b || reg == 0x3f || reg == 0x43))
#endif
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
		    || (!log && a6_power_stock_off_reg(reg, true))
#endif
		    )) return -EINVAL;
	} else if (reg != 0x1e && reg != 0 && reg != 0x22 && reg != 0x23 &&
		   reg != 0x68 && reg != 0x7f
#ifdef A6_CHARGER_PROOF
		   && reg != 0x1b && reg != 0x3f && reg != 0x43 &&
		   reg != 0x45 && reg != 0x46
#endif
#ifdef A6_D1972_POLICY
		   && reg != 0x1b && reg != 0x3f && reg != 0x43 &&
		   reg != 0x45 && reg != 0x46 &&
		   !a6_power_shutdown_read_reg(reg)
#endif
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
		   && !a6_power_stock_off_reg(reg, false)
#endif
#ifdef A6_D1972_VBUS_ADC
		   && reg != 0x48 && reg != 0x49 && reg != 0x4a
#endif
		   ) return -EINVAL;
	if (log && a6_power_transactions >= A6_POWER_MAX) return -EOVERFLOW;
	s = readl(a6_touch_i2c+0x14);
	if (!a6_power_is_idle(s)) return -EBUSY;
	if (log) {
		slot = a6_power_transactions++;
		a6_power_regs[slot] = reg; a6_power_writes[slot] = write;
		if (write) a6_power_values[slot] = *value;
	}
	writel(s, a6_touch_i2c+0x14);
	writel(0x1e8, a6_touch_i2c);
	if (write) {
		/* One ordinary two-byte I2C write: pointer, data|STOP. */
		writel(reg, a6_touch_i2c);
		writel(0x200|*value, a6_touch_i2c);
	} else {
		writel(0x200|reg, a6_touch_i2c);
		writel(0x1e9, a6_touch_i2c);
		writel(0x601, a6_touch_i2c);
		needed |= A6_POWER_XEN|A6_POWER_RX;
	}
	for (i = 0; i < 10000; i++) {
		s = readl(a6_touch_i2c+0x14);
		if (log) { a6_power_status[slot] = s; a6_power_polls++; }
		if (s == U32_MAX) return -EIO;
		if (s & A6_POWER_ERR) return (s & (1U<<21)) ? -ENXIO : -EIO;
		if (!(s & A6_POWER_XIP) && (s & needed) == needed) break;
		udelay(10);
	}
	if (i == 10000) return -ETIMEDOUT;
	if (write) {
		if (s & A6_POWER_RX) return -EIO;
	} else {
		d = readl(a6_touch_i2c+4);
		if (d & ~0xffU) return -ENODATA;
		*value = d;
		if (log) a6_power_values[slot] = d;
	}
	writel(A6_POWER_XEN, a6_touch_i2c+0x14);
	return 0;
}
#ifdef A6_D1972_STOCK_OFF_CANDIDATE
/* One bounded FIFO transaction, matching stock's register-pointer plus
 * contiguous data transfer. Only the two recovered shutdown blocks fit.
 */
static int a6_power_stock_off_block(u8 reg, const u8 *data, size_t len)
{
	u32 s;
	size_t j;
	unsigned int i;

	if (!((reg == 0x12 && len == 9) || (reg == 0x68 && len == 12)))
		return -EINVAL;
	s = readl(a6_touch_i2c + 0x14);
	if (!a6_power_is_idle(s))
		return -EBUSY;
	writel(s, a6_touch_i2c + 0x14);
	writel(0x1e8, a6_touch_i2c);
	writel(reg, a6_touch_i2c);
	for (j = 0; j < len; j++)
		writel(data[j] | (j + 1 == len ? 0x200 : 0), a6_touch_i2c);
	for (i = 0; i < 10000; i++) {
		s = readl(a6_touch_i2c + 0x14);
		if (s == U32_MAX)
			return -EIO;
		if (s & A6_POWER_ERR)
			return (s & (1U << 21)) ? -ENXIO : -EIO;
		if (!(s & A6_POWER_XIP) &&
		    (s & (A6_POWER_XEN | A6_POWER_TX)) ==
		    (A6_POWER_XEN | A6_POWER_TX))
			break;
		udelay(10);
	}
	if (i == 10000)
		return -ETIMEDOUT;
	if (s & A6_POWER_RX)
		return -EIO;
	writel(A6_POWER_XEN, a6_touch_i2c + 0x14);
	return 0;
}
#endif
static int a6_power_byte(u8 reg, u8 *value, bool write)
{
	return a6_power_xfer(reg, value, write, true);
}
static int a6_power_set(u8 reg, u8 value)
{
	return a6_power_byte(reg, &value, true);
}
static int a6_power_start(void)
{
	static const u8 regs[] = {0x1e, 0, 0x22, 0x23, 0x68, 0x7f};
	unsigned int i;
	int ret;
	for (i = 0; i < ARRAY_SIZE(regs); i++) {
		ret = a6_power_byte(regs[i], &a6_power_before[i], false);
		if (ret) goto out;
		/* Registers68/7f are bank-specific: never read them in bank1. */
		if (!i && a6_power_before[0] != 0) { ret = -EPROTO; goto out; }
	}
	if (a6_power_before[1] != 0x34 || a6_power_before[2] != 0xeb ||
	    a6_power_before[3] != 0xad) { ret = -EPROTO; goto out; }
	a6_power_saved = true;
	/* Stock power-on is analog first, then LDO. Inherited bit40 and bit08
	 * remain set, satisfying the stock shared-bit rule in both directions.
	 */
	a6_power_maybe_ana = true;
	ret = a6_power_set(0x22, 0xef);
	if (ret) goto out;
	ret = a6_power_byte(0x22, &a6_power_enabled[0], false);
	if (ret) goto out;
	if (a6_power_enabled[0] != 0xef) { ret = -EIO; goto out; }
	msleep(1);
	a6_power_maybe_ldo = true;
	ret = a6_power_set(0x23, 0xed);
	if (ret) goto out;
	ret = a6_power_byte(0x23, &a6_power_enabled[1], false);
	if (!ret && a6_power_enabled[1] != 0xed) ret = -EIO;
	if (!ret) msleep(20);
out:
	a6_power_start_result = ret;
	return ret;
}
static bool a6_power_recover(void)
{
	u32 s = readl(a6_touch_i2c+0x14);
	if (!a6_power_is_idle(s)) {
		writel(0x704, a6_touch_i2c+0x1c);
		udelay(10);
		writel(0x104, a6_touch_i2c+0x1c);
		s = readl(a6_touch_i2c+0x14);
	}
	if (s != U32_MAX) writel(s, a6_touch_i2c+0x14);
	return a6_power_is_idle(readl(a6_touch_i2c+0x14));
}
static bool a6_power_restore(void)
{
	static const u8 regs[] = {0x22, 0x23, 0x1e, 0x68, 0x7f};
	unsigned int i;
	int ret;
	bool ok = a6_power_recover();
	/* Best-effort reverse-order restore of every potentially written byte.
	 * Each restore is attempted at most once; stop forward progress on error.
	 * A failed LDO restore must not prevent attempting analog restoration.
	 */
	if (a6_power_maybe_ldo) {
		ret = a6_power_set(0x23, 0xad);
		if (ret) { a6_power_cleanup_result = ret; ok = false; }
		if (!a6_power_recover()) ok = false;
	}
	if (a6_power_maybe_ana) {
		ret = a6_power_set(0x22, 0xeb);
		if (ret) { a6_power_cleanup_result = ret; ok = false; }
		if (!a6_power_recover()) ok = false;
	}
	if (a6_power_saved) {
		for (i = 0; i < ARRAY_SIZE(regs); i++) {
			ret = a6_power_byte(regs[i], &a6_power_after[i], false);
			if (ret) { a6_power_cleanup_result = ret; ok = false; break; }
			if (i == 2 && a6_power_after[i] != 0) { ok = false; break; }
		}
		if (i != ARRAY_SIZE(regs) || a6_power_after[0] != 0xeb ||
		    a6_power_after[1] != 0xad || a6_power_after[2] != 0 ||
		    a6_power_after[3] != a6_power_before[4] ||
		    a6_power_after[4] != a6_power_before[5]) ok = false;
	}
	a6_power_idle = a6_power_recover();
	a6_power_config_ok = readl(a6_touch_i2c+0x1c) == 0x104 &&
		readl(a6_touch_i2c+0x18) == 0 && readl(a6_touch_i2c+0x28) == 1 &&
		readl(a6_touch_pmgr+A6_TOUCH_I2C_GATE) == 0x2ff &&
		readl(a6_touch_gpio+0xe8) == 0x221 && readl(a6_touch_gpio+0xec) == 0x221;
	a6_power_restored = ok && a6_power_idle && a6_power_config_ok;
	return a6_power_restored;
}
static ssize_t a6_power_report(char *buf, ssize_t n)
{
	unsigned int i;
	n += sysfs_emit_at(buf, n, "power_saved=%u ana_maybe_written=%u ldo_maybe_written=%u power_start_result=%d power_cleanup_result=%d power_restored=%u i2c_idle=%u i2c_config=%u transactions=%u polls=%u\n",
		a6_power_saved, a6_power_maybe_ana, a6_power_maybe_ldo,
		a6_power_start_result, a6_power_cleanup_result, a6_power_restored,
		a6_power_idle, a6_power_config_ok, a6_power_transactions, a6_power_polls);
	n += sysfs_emit_at(buf, n, "power_before_bank_id_22_23_68_7f=%*phN enabled_22_23=%*phN after_22_23_bank_68_7f=%*phN\n",
		6, a6_power_before, 2, a6_power_enabled, 5, a6_power_after);
	for (i = 0; i < a6_power_transactions; i++)
		n += sysfs_emit_at(buf, n, "pmu_op%u=%c:%02x:%02x status=%08x\n", i,
			a6_power_writes[i] ? 'w' : 'r', a6_power_regs[i], a6_power_values[i], a6_power_status[i]);
	return n;
}

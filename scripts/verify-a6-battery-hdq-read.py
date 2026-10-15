#!/usr/bin/env python3
from pathlib import Path
import hashlib
import re
import sys

repo = Path(__file__).resolve().parents[1]
kind = sys.argv[1] if len(sys.argv) > 1 else "battery-hdq-read"
assert kind in ("battery-hdq-read", "battery-hdq-line-observer")
src = (repo / "kernel/platform/a6-battery-hdq-read.inc").read_text()
config = (repo / f"build/linux-a6-{kind}/.config").read_text()
image = (repo / f"build/linux-a6-{kind}/vmlinux").read_bytes()
pmu = (repo / "build/touch-research/ios10-touch-dependencies/com.apple.driver.AppleD1972PMU.macho").read_bytes()
assert hashlib.sha256(pmu).hexdigest() == "3df8f04a9759008493575f3078e3416e935fa450a366ea4d5356cb84ca628c16"
pmu_base = 0x810e3000
def pmu_bytes(address, expected):
    actual = pmu[address-pmu_base:address-pmu_base+len(expected)]
    assert actual == expected, (hex(address), actual.hex(), expected.hex())
# Virtual GPIO register mapper: indices 0..11 map to PMU 0x68..0x73.
pmu_bytes(0x810e7678, bytes.fromhex("0b2901f1680088bf4ff6ff707047"))
# GPIO platform function normalizes *arg1 and dispatches provider,index,value,polarity.
pmu_bytes(0x810e897c, bytes.fromhex("6069a369d3f808900a68002a18bf01225b7b002b18bf01234946fef75fff"))

for needle in (
    "A6_BATTERY_HDQ_READ_V9", "read-basic-once", "0x32a00000",
    "0x3f101000", "0x3fa00000", "0x10c", "0x0b0",
    "encoded[i] = command & BIT(i) ? 0xfe : 0xc0",
    "udelay(200)", "udelay(40)",
    "count < 8 || count > 16",
    "A6_HDQ_TXFULL    BIT(9)", "A6_HDQ_RXFULL    BIT(8)",
    "count = state & A6_HDQ_RXMASK", "writel(encoded[i]",
    "readl(a6_hdq_uart + A6_HDQ_URXH)",
    "stage=%u last_utrstat=%08x last_ufstat=%08x",
    "A6_HDQ_TXRESET   BIT(2)", "tx_wait_us[] = { 1000, 2000, 7000, 20000, 70000 }",
    "tx%u utrstat=%08x ufstat=%08x",
    "rx_wait_us[] = { 250, 500, 1000, 2000, 3000 }",
    "rx%u ufstat=%08x", "break_error=%08x",
    "RESETRX is self-clearing", "rx_reset=%d rx_reset_ufcon=%08x",
    "Apple's matching driver requests 115200 half-bits/s",
    "writel(0x33, a6_hdq_uart + A6_HDQ_UBRDIV)",
    "writel(0x60, a6_hdq_uart + A6_HDQ_UTRSTAT)",
    "a6_hdq_tx_fifo_reset()", "a6_hdq_apple_preflush()",
    "programmed_ubrdiv=%08x programmed_udivslot=%08x",
    "A6_HDQ_I2C_BASE  0x33200000", "A6_HDQ_PMU_REG   0x6d",
    "a6_hdq_pmu_asserted = (a6_hdq_pmu_saved & (u8)~0xfd) | 0x18 | 0x02",
    "a6_hdq_pmu_asserted != 0x1a",
    "a6_hdq_pmu_restore();", "pmu_restored=%u i2c_idle=%u",
    "voltage_mv=%u soc_percent=%u", "__ATTR(status, 0400",
    "__ATTR(run, 0200",
):
    assert needle in src, needle
assert "read-basic-once" in src
assert "CONFIG_POWER_SUPPLY is not set" in config
assert "CONFIG_REGULATOR is not set" in config
marker = b"A6_BATTERY_HDQ_LINE_V1" if kind == "battery-hdq-line-observer" else b"A6_BATTERY_HDQ_READ_V9"
assert marker in image
assert image.count(marker) == 1
assert b"A6_BATTERY_HDQ_READ_V8" not in image
assert b"A6_BATTERY_HDQ_READ_V7" not in image
assert b"A6_BATTERY_HDQ_READ_V6" not in image
assert b"A6_BATTERY_HDQ_READ_V5" not in image
assert b"read-basic-once" in image
assert b"read-n1-version" not in image
assert "a6_hdq_gpio +" not in "\n".join(
    line for line in src.splitlines() if re.search(r"\bwrite[bl]\s*\(", line))
assert "a6_hdq_pmgr +" not in "\n".join(
    line for line in src.splitlines() if re.search(r"\bwrite[bl]\s*\(", line))
assert set(re.findall(r"a6_hdq_read_byte\(commands\[i\], i\)", src)) == {
    "a6_hdq_read_byte(commands[i], i)"
}
assert src.count("a6_hdq_pmu_byte(0x1e, &a6_hdq_pmu_bank, false)") == 1
print("PASS battery HDQ read: Apple encoding/timing, exact D1972 SWI request, bounded FIFO, PMU/UART restoration, no charger write")

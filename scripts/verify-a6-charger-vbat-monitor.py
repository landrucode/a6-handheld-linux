#!/usr/bin/env python3
"""Check the opt-in repeatable VBAT observer and cached battery property."""
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[1]
monitor = (repo / "kernel/platform/a6-d1972-vbat-adc.inc").read_text()
supply = (repo / "kernel/platform/a6-d1972-battery-supply.inc").read_text()
assert "sample-vbat-and-restore" in monitor
assert "time_before(jiffies, a6_vbat_next_jiffies)" in monitor
assert "a6_vbat_result || !a6_vbat_restored" in monitor
assert "a6_vbat_next_jiffies = jiffies + 60 * HZ" in monitor
assert "a6_vbus_xfer(0x48, &restore, true)" in monitor
assert "POWER_SUPPLY_PROP_VOLTAGE_NOW" in supply
assert "!a6_vbat_samples || a6_vbat_result || !a6_vbat_restored" in supply
assert "(u64)a6_vbat_raw * 32000000 / 65536" in supply
assert 2500000 + 2427 * 32000000 // 65536 == 3685058
kind = sys.argv[1] if len(sys.argv) > 1 else "charger-vbat-monitor"
assert kind in ("charger-vbat-monitor", "charger-vbat-hdq-phase", "charger-vbat-hdq-timed", "charger-vbat-hdq-echo-guard", "charger-vbat-hdq-tx-turnaround", "charger-vbat-backlight-trial", "touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42")
linked = (repo / f"build/linux-a6-{kind}/vmlinux").read_bytes()
assert linked.count(b"A6_D1972_VBAT_ADC_V1") == 1
assert linked.count(b"sample-vbat-and-restore") == 1
assert linked.count(b"a6-d1972-battery") >= 1
print("PASS: 60-second guarded VBAT sampling and cached battery voltage linked")

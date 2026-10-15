#!/usr/bin/env python3
"""Check the opt-in one-shot VBUS ADC observer in the linked image."""
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
kind = sys.argv[1] if len(sys.argv) > 1 else "charger-vbus-adc"
assert kind in ("charger-vbus-adc", "charger-vbat-adc", "charger-vbat-monitor", "charger-vbat-hdq-phase", "charger-vbat-hdq-timed", "charger-vbat-hdq-echo-guard", "charger-vbat-hdq-tx-turnaround", "charger-vbat-backlight-trial", "touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42")
build = repo / f"build/linux-a6-{kind}"
source = (repo / "kernel/platform/a6-d1972-vbus-adc.inc").read_text()
assert "sample-vbus-once-and-restore" in source
assert "a6_vbus_before[0] & 0x60" in source
assert "a6_vbus_restored" in source
assert "a6_vbus_xfer(0x48, &restore, true)" in source
linked = (build / "vmlinux").read_bytes()
assert linked.count(b"A6_D1972_VBUS_ADC_V1") == 1
assert linked.count(b"sample-vbus-once-and-restore") == 1
subprocess.run(["python3", str(repo / "scripts/verify-a6-charger-usb-power.py"), kind], check=True)
print("PASS: opt-in one-shot D1972 VBUS ADC observer linked")

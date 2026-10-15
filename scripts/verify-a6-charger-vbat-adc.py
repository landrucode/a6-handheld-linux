#!/usr/bin/env python3
"""Check the opt-in one-shot VBAT observer in the linked image."""
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / "kernel/platform/a6-d1972-vbat-adc.inc").read_text()
assert "sample-vbat-once-and-restore" in source
assert "a6_vbat_before[0] & 0x60" in source
assert "a6_vbat_xfer" not in source
assert "a6_vbus_xfer(0x48, &restore, true)" in source
assert "verify == a6_vbat_before[0]" in source
linked = (repo / "build/linux-a6-charger-vbat-adc/vmlinux").read_bytes()
assert linked.count(b"A6_D1972_VBAT_ADC_V1") == 1
assert linked.count(b"sample-vbat-once-and-restore") == 1
print("PASS: opt-in one-shot D1972 VBAT ADC observer linked")

#!/usr/bin/env python3
"""Check the optional raw GPIO44 observation around the unchanged HDQ trial."""
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = (repo / "kernel/platform/a6-battery-hdq-read.inc").read_text()
linked = (repo / "build/linux-a6-battery-hdq-line-observer/vmlinux").read_bytes()
assert "A6_HDQ_LINE_SAMPLES 128" in source
assert "readl(a6_hdq_gpio + A6_HDQ_GPIO44)" in source
assert "bit0_bitmap=%08x,%08x,%08x,%08x" in source
assert "a6_hdq_line_before = gpio" in source
assert "a6_hdq_line_requested = readl" in source
assert "a6_hdq_line_after = readl" in source
assert linked.count(b"A6_BATTERY_HDQ_LINE_V1") == 1
assert b"A6_BATTERY_HDQ_READ_V9" not in linked
assert b"line_gpio_before=" in linked
print("PASS: raw GPIO44 sampling linked to the bounded HDQ trial")

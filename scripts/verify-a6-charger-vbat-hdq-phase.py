#!/usr/bin/env python3
"""Check the combined guarded VBAT monitor and phase-separated HDQ observer."""
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[1]
kind = sys.argv[1] if len(sys.argv) > 1 else "charger-vbat-hdq-phase"
assert kind in ("charger-vbat-hdq-phase", "charger-vbat-hdq-timed", "charger-vbat-hdq-echo-guard", "charger-vbat-hdq-tx-turnaround", "touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42")
source = (repo / "kernel/platform/a6-battery-hdq-read.inc").read_text()
builder = (repo / "scripts/build-a6-zimage.sh").read_text()
config = (repo / f"build/linux-a6-{kind}/.config").read_text()
linked = (repo / f"build/linux-a6-{kind}/vmlinux").read_bytes()

assert "CONFIG_POWER_SUPPLY=y" in config
assert "#define A6_HDQ_WITH_VBAT_MONITOR 1" in builder
assert "#define A6_HDQ_PHASE_OBSERVER 1" in builder
assert "static struct mutex a6_touch_lock;" in source
assert "mutex_lock(&a6_touch_lock);" in source
assert "mutex_unlock(&a6_touch_lock);" in source
for phase, samples in ((0, 20), (1, 4), (2, 128), (3, 128)):
    needle = f"a6_hdq_capture_phase({phase}, "
    assert needle in source
assert "phase%u count=%u elapsed_us=%u" in source
assert "a6_hdq_pmu_restore();" in source
assert "a6_hdq_restore();" in source
marker = (b"A6_BATTERY_HDQ_TX_TURNAROUND_V5" if kind == "charger-vbat-hdq-tx-turnaround" else
          b"A6_BATTERY_HDQ_ECHO_GUARD_V4" if kind in ("charger-vbat-hdq-echo-guard", "touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42") else
          b"A6_BATTERY_HDQ_TIMED_V3" if kind.endswith("-timed") else
          b"A6_BATTERY_HDQ_PHASE_V2")
assert linked.count(marker) == 1
if kind.endswith(("-timed", "-echo-guard", "-tx-turnaround")) or kind in ("touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42"):
    assert "a6_hdq_wait_until" in source
    assert "div_u64(ktime_get_ns() - start, 1000)" in source
    assert "#define A6_HDQ_REALTIME_US 1" in builder
if kind.endswith(("-echo-guard", "-tx-turnaround")) or kind in ("touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42"):
    assert "a6_hdq_raw[slot][i] != encoded[i]" in source
    assert "if (count != 16)" in source
    assert "return -ENODATA;" in source
    assert "voltage < 2500 || voltage > 4500" in source
if kind.endswith("-tx-turnaround"):
    assert "#define A6_HDQ_TX_TURNAROUND 1" in builder
    assert "u64 deadline = ktime_get_ns() + 5000000" in source
    assert "#ifndef A6_HDQ_TX_TURNAROUND\n\tif (!slot) {\n\t\tret = a6_hdq_capture_phase(2," in source
    assert "if (ucon != 0x405)" in source
    assert "a6_hdq_tx_disabled != 0x401" in source
    assert "a6_hdq_tx_reenabled != ucon" in source
    assert linked.count(b"tx_disabled=%08x tx_reenabled=%08x") == 1
assert linked.count(b"A6_D1972_VBAT_ADC_V1") == 1
assert linked.count(b"sample-vbat-and-restore") == 1
assert linked.count(b"a6-d1972-battery") >= 1
assert b"phase%u count=%u elapsed_us=%u" in linked
assert b"A6_BATTERY_HDQ_LINE_V1" not in linked
print("PASS: shared-lock VBAT monitor and four-phase one-shot HDQ observer linked")

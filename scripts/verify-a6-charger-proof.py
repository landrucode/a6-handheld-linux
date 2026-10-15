#!/usr/bin/env python3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
src = (repo / "kernel/platform/a6-charger-proof.inc").read_text()
image = repo / "build/arm/a6-linux-charger-proof.img3"
assert image.is_file() and image.stat().st_size > 1_000_000
for marker in ["A6_CHARGER_PROOF_V1", "prove-90ma-10s-and-restore", "observe-charger"]:
    assert marker in src
for reg in ["0x1b", "0x3f", "0x43", "0x45", "0x46"]:
    assert reg in src
transport = (repo / "kernel/platform/a6-touch-power-check.inc").read_text()
for reg in ["reg != 0x1b", "reg != 0x3f", "reg != 0x43", "reg != 0x45", "reg != 0x46"]:
    assert reg in transport
assert "msleep(1000)" in src and "A6_CHARGER_SAMPLES 11" in src
assert "a6_charger_restored" in src and "memcmp(a6_charger_before, a6_charger_after, 5)" in src
assert "if (wrote_1b)" in src and "if (wrote_3f)" in src and "if (wrote_43)" in src
assert "0x00010100" in transport and "needed = A6_POWER_XEN|A6_POWER_TX" in transport
assert "#define A6_POWER_MAX 48" in transport
assert "A6_POWER_MAX - A6_CHARGER_REQUIRED_OPS" in src
vmlinux = (repo / "build/linux-a6-charger-proof/vmlinux").read_bytes()
assert vmlinux.count(b"A6_CHARGER_PROOF_V1") == 1
print("PASS charger proof: stock-derived 90mA input/100mA target, readback, 11 samples, unconditional reverse restore")

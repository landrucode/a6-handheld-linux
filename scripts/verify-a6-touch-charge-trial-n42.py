#!/usr/bin/env python3
"""Verify the opt-in charger trial is isolated from the working RAM image."""
from pathlib import Path
import re
import subprocess

repo = Path(__file__).resolve().parents[1]
kind = "touch-charge-trial-n42"
image = repo / f"build/arm/a6-linux-{kind}.img3"
linked = repo / f"build/linux-a6-{kind}/vmlinux"
source = (repo / "kernel/platform/a6-charger-proof.inc").read_text()
assert image.is_file() and image.stat().st_size > 1_000_000
assert linked.is_file()
data = linked.read_bytes()
assert data.count(b"A6_CHARGER_ACTIVE_TRIAL_V1") == 1
assert data.count(b"prove-480in-200charge-10s-and-restore") == 1
assert data.count(b"reported_limit_samples_ma=") == 1
assert b"A6_CHARGER_PROOF_V1" not in data
assert b"prove-90ma-10s-and-restore" not in data
for marker in (b"A6_TOUCH_N42_FW_V1", b"A6_TOUCH_N42_POST_V1",
               b"A6_TOUCH_N42_REPORT_PROBE_V1", b"A6_TOUCH_N42_CAL_V1",
               b"A6_D1972_VBAT_ADC_V1", b"A6_D1972_VBUS_ADC_V1"):
    assert data.count(marker) == 1, marker
assert (repo / f"build/linux-a6-{kind}/.config").read_text().count("CONFIG_USB_CDC_COMPOSITE=y") == 1
obj = repo / f"build/linux-a6-{kind}/drivers/usb/gadget/legacy/cdc2.o"
sections = subprocess.check_output(["llvm-readelf", "--sections", "--wide", str(obj)], text=True)
match = re.search(r"\]\s+\.data\.cdc_config_driver\s+PROGBITS\s+\S+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)", sections)
assert match
offset, size = (int(part, 16) for part in match.groups())
descriptor = obj.read_bytes()[offset:offset + size]
assert descriptor[0x16] == 0x80 and int.from_bytes(descriptor[0x18:0x1c], "little") == 500
for text in (
    "#define A6_CHARGER_INPUT_CODE 16",
    "#define A6_CHARGER_TARGET_CODE 13",
    "a6_charger_before[2] != 0x3f",
    "A6_POWER_MAX - A6_CHARGER_REQUIRED_OPS",
    "if (wrote_1b)", "if (wrote_3f)", "if (wrote_43)",
    "memcmp(a6_charger_before, a6_charger_after, 5)",
):
    assert text in source, text
assert (repo / "build/arm/a6-linux-touch-clk32-n42.img3").is_file()
print("PASS isolated N42 480mA input/200mA target trial: linked marker, one-shot guard, reverse restoration, working image retained")

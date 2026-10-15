#!/usr/bin/env python3
"""Check the linked power-supply code and the compiled CDC power descriptor."""
from pathlib import Path
import re
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
kind = sys.argv[1] if len(sys.argv) > 1 else "charger-usb-power"
assert kind in ("charger-usb-power", "charger-vbus-adc", "charger-vbat-adc", "charger-vbat-monitor", "charger-tbat-adc", "charger-policy-500", "stock-off-candidate", "low-battery-candidate", "low-battery-vbus-bridge", "low-battery-bvalid", "low-battery-bvalid-screen", "low-battery-reset-trace", "low-battery-reset-stage", "low-battery-auto-recover", "low-battery-boot-defaults", "low-battery-vbus-full-speed", "low-battery-vbus-screen", "low-battery-trace", "usb-reconnect-screen", "usb-reconnect-ep0", "usb-reconnect-rearm", "usb-reconnect-phy", "usb-reconnect-enum-rearm", "usb-reconnect-vbus-latch", "usb-reconnect-lx-latch", "usb-reconnect-lx-rearm", "usb-reconnect-l3-rearm", "charger-vbat-hdq-phase", "charger-vbat-hdq-timed", "charger-vbat-hdq-echo-guard", "charger-vbat-hdq-tx-turnaround", "charger-vbat-backlight-trial", "touch-fw-n42", "touch-post-n42", "touch-report-n42", "touch-full-n42", "touch-retry-n42", "touch-clk32-n42", "touch-e3-info-n42")
build = repo / f"build/linux-a6-{kind}"
obj = build / "drivers/usb/gadget/legacy/cdc2.o"
sections = subprocess.check_output(
    ["llvm-readelf", "--sections", "--wide", str(obj)], text=True
)
match = re.search(
    r"\]\s+\.data\.cdc_config_driver\s+PROGBITS\s+\S+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)",
    sections,
)
assert match, "CDC configuration descriptor object section missing"
offset, size = (int(x, 16) for x in match.groups())
data = obj.read_bytes()[offset : offset + size]
# usb_configuration: bConfigurationValue, bmAttributes and MaxPower.
assert data[0x14] == 1
assert data[0x16] == 0x80, f"expected bus-powered; got {data[0x16]:02x}"
assert int.from_bytes(data[0x18:0x1c], "little") == 500
config = (build / ".config").read_text()
assert "CONFIG_POWER_SUPPLY=y" in config
assert "CONFIG_USB_CDC_COMPOSITE=y" in config
vmlinux = (build / "vmlinux").read_bytes()
assert vmlinux.count(b"a6-d1972-usb") == 1
if kind in ("charger-policy-500", "stock-off-candidate", "low-battery-candidate", "low-battery-vbus-bridge", "low-battery-bvalid", "low-battery-bvalid-screen", "low-battery-reset-trace", "low-battery-reset-stage", "low-battery-auto-recover", "low-battery-boot-defaults", "low-battery-vbus-full-speed", "low-battery-vbus-screen", "low-battery-trace", "usb-reconnect-screen", "usb-reconnect-ep0", "usb-reconnect-rearm", "usb-reconnect-phy", "usb-reconnect-enum-rearm", "usb-reconnect-vbus-latch", "usb-reconnect-lx-latch"):
    assert vmlinux.count(b"A6_D1972_500_CLASS_CANDIDATE_V5") == 1
    assert b"A6_D1972_AUTO_SAMPLES_V1" in vmlinux
    assert b"A6_D1972_SHUTDOWN_REGS_V2" in vmlinux
    assert b"a6-d1972: power-off request 0x1b|=1" in vmlinux
    if kind in ("stock-off-candidate", "low-battery-candidate", "low-battery-vbus-bridge", "low-battery-bvalid", "low-battery-bvalid-screen", "low-battery-reset-trace", "low-battery-reset-stage", "low-battery-auto-recover", "low-battery-boot-defaults", "low-battery-vbus-full-speed", "low-battery-vbus-screen", "low-battery-trace"):
        assert vmlinux.count(b"A6_STOCK_OFF_CANDIDATE_V1") == 1
        assert b"arm-unplugged-once\0" in vmlinux
        assert b"a6-d1972: stock-off stage=" in vmlinux
    if kind in ("low-battery-candidate", "low-battery-vbus-bridge", "low-battery-bvalid", "low-battery-bvalid-screen", "low-battery-reset-trace", "low-battery-reset-stage", "low-battery-auto-recover", "low-battery-boot-defaults", "low-battery-vbus-full-speed", "low-battery-vbus-screen", "low-battery-trace"):
        assert vmlinux.count(b"A6_LOW_BATTERY_CANDIDATE_V3") == 1
        assert b"attended-trial-once\0" in vmlinux
        assert b"attended-plugged-trial-once\0" in vmlinux
        assert b"plugged_critical_mv=%u" in vmlinux
        assert b"a6 plugged low battery" in vmlinux
        assert b"low-battery stock-off failed; trying iOS reset" in vmlinux
    if kind == "low-battery-trace":
        assert b"A6_LOW_BATTERY_TRACE_SCREEN_V1" in vmlinux
    if kind in ("low-battery-vbus-bridge", "low-battery-bvalid", "low-battery-bvalid-screen", "low-battery-reset-trace", "low-battery-reset-stage", "low-battery-auto-recover", "low-battery-boot-defaults", "low-battery-vbus-full-speed", "low-battery-vbus-screen"):
        assert vmlinux.count(b"A6 VBUS bridge: source=%d") == 1
    if kind in ("low-battery-bvalid", "low-battery-bvalid-screen"):
        assert vmlinux.count(b"A6 BVALID override: source=%u") == 1
    if kind in ("low-battery-vbus-screen", "low-battery-bvalid-screen", "low-battery-reset-trace"):
        assert b"a6_usb_reconnect_trace" in vmlinux
    if kind in ("low-battery-reset-trace", "low-battery-reset-stage", "low-battery-auto-recover", "low-battery-boot-defaults"):
        assert b"a6_usb_core_reset_trace" in vmlinux
    if kind in ("low-battery-auto-recover", "low-battery-boot-defaults"):
        assert b"A6 USB recovery: invalid session" in vmlinux
        assert b"a6_usb_udc_cycle" in vmlinux
    if kind == "low-battery-boot-defaults":
        assert b"A6_BOOT_DEFAULTS_V1 auto=1 monitor=1" in vmlinux
    assert b"arm-500-class-10m-after-tbat-check\0" in vmlinux
    assert b"rearm-500-class-10m-after-tbat-check\0" in vmlinux
    assert b"A6_CHARGER_PROOF_V1" not in vmlinux
    if kind in ("usb-reconnect-screen", "usb-reconnect-ep0", "usb-reconnect-rearm", "usb-reconnect-phy", "usb-reconnect-enum-rearm", "usb-reconnect-vbus-latch", "usb-reconnect-lx-latch"):
        assert b"a6_usb_reconnect_trace" in vmlinux
    if kind in ("usb-reconnect-lx-latch", "usb-reconnect-lx-rearm", "usb-reconnect-l3-rearm"):
        assert b"a6_usb_lx_trace" in vmlinux
else:
    assert vmlinux.count(b"A6_CHARGER_PROOF_V1") == 1
source = (repo / "kernel/platform/a6-d1972-power-supply.inc").read_text()
assert "a6_power_xfer(0x43, &code, false, false)" in source
assert "set_property" not in source
print("PASS: bus-powered 500 mA CDC descriptor and read-only D1972 power_supply")

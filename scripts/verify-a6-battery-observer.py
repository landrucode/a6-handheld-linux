#!/usr/bin/env python3
from pathlib import Path
import re

repo = Path(__file__).resolve().parents[1]
src = (repo / "kernel/platform/a6-battery-observer.inc").read_text()
config = (repo / "build/linux-a6-battery-observer/.config").read_text()
image = (repo / "build/linux-a6-battery-observer/vmlinux").read_bytes()

required = {
    "uart_base": "#define A6_BATTERY_UART_BASE 0x32a00000",
    "gate": "#define A6_BATTERY_UART_GATE 0x10c",
    "gpio44": "#define A6_BATTERY_GPIO44    0x0b0",
    "command": 'sysfs_streq(buf, "enable-uart5")',
    "status_mode": "__ATTR(status, 0400",
    "command_mode": "__ATTR(enable_clock, 0200",
    "marker": '"A6_BATTERY_OBSERVER_V1\\n"',
}
for name, needle in required.items():
    assert needle in src, (name, needle)

assert "readl(a6_battery_uart + 0x20)" not in src
assert "readl(a6_battery_uart + 0x24)" not in src
assert re.findall(r"\bwritel\s*\(", src) == ["writel("]
assert "a6_battery_pmgr + A6_BATTERY_UART_GATE" in src
assert "a6_battery_uart + A6_BATTERY_UART_GATE" not in src
assert "CONFIG_POWER_SUPPLY is not set" in config
assert "CONFIG_REGULATOR is not set" in config
assert b"A6_BATTERY_OBSERVER_V1" in image
assert b"enable-uart5" in image
assert b"read-n1-version" not in image

print("PASS battery observer: fixed n42 UART5/gate/GPIO, root-only one-shot, no FIFO/status/gauge/charger access")

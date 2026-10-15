#!/usr/bin/env python3
"""Verify the separate, guarded N42 DWI backlight RAM candidate."""
from pathlib import Path
import hashlib
import re
import subprocess

root = Path(__file__).resolve().parents[1]
source = (root / "kernel/platform/a6-backlight-trial.inc").read_text()
builder = (root / "scripts/build-a6-zimage.sh").read_text()
linked = (root / "build/linux-a6-charger-vbat-backlight-trial/vmlinux").read_bytes()
stock_dwi = (root / "build/touch-research/ios10-power-dependencies/com.apple.driver.AppleS5L8940XDWI.macho").read_bytes()
assert hashlib.sha256(stock_dwi).hexdigest() == "6b00e9ba3dd08544e35294f4edfa0d045f94ec5a3130357b121427f6ae0f6168"
stock_tree = (root / ".deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw").read_bytes()
assert hashlib.sha256(stock_tree).hexdigest() == "a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef"
import importlib.util
import struct
spec = importlib.util.spec_from_file_location("platform_tree", root / "scripts/inspect-a6-platform-tree.py")
tree_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tree_module)
nodes = tree_module.parse_tree(stock_tree)
assert nodes['/device-tree/arm-io']['ranges'] == struct.pack('<III', 0, 0x30000000, 0x10000000)
assert nodes['/device-tree/arm-io/dwi']['reg'] == struct.pack('<II', 0x0f700000, 0x1000)
assert 0x30000000 + 0x0f700000 == 0x3f700000
disasm = subprocess.check_output(['llvm-objdump', '-dr', str(root / 'build/linux-a6-charger-vbat-backlight-trial/drivers/video/fbdev/fb-apple-a6.o')], text=True)
init = disasm.split('<a6_bl_init>:', 1)[1]
init = re.split(r'\n[0-9a-f]+ <', init, maxsplit=1)[0]
assert re.search(r'movt\s+r0, #0x3f70\b', init)
assert 'ioremap' in init
name = stock_tree.find(b"DWI\0")
assert name >= 28 and stock_tree.find(b"DWI\0", name + 1) == -1
row = stock_tree[name - 28:name + 16]
assert len(row) == 44 and row[3] == 0x7f and int.from_bytes(row[12:16], "little") == 0x4d
assert "A6_BACKLIGHT_TRIAL" in builder
assert linked.count(b"A6_BACKLIGHT_DWI_TRIAL_V4") == 1
assert linked.count(b"dim-half-5s-and-restore") == 1
assert linked.count(b"A6_D1972_VBAT_ADC_V1") == 1
assert b"A6_BATTERY_HDQ" not in linked
for required in (
    "A6_BL_DWI_BASE 0x3f700000", "A6_BL_DWI_GATE 0x134",
    "A6_BL_WLED_COMMAND 0x71", "A6_BL_VERSION1_PREFIX 0xa0000000U",
    "a6_bl_before_cmd != 0x70", "a6_bl_before_data & ~0x7ffU",
    "writel(a6_bl_before_data, a6_bl_dwi + A6_BL_DATA)",
    "a6_bl_after_data == a6_bl_before_data", "a6_bl_attempted = true",
    "writel(gate_check | 0xf, a6_bl_pmgr + A6_BL_DWI_GATE)",
    "writel(a6_bl_gate_before, a6_bl_pmgr + A6_BL_DWI_GATE)",
    "mutex_lock(&a6_touch_lock)", "mutex_unlock(&a6_touch_lock)",
):
    assert required in source, required
print("PASS: N42 DWI backlight trial, exact-state guard and rollback linked")

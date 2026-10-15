#!/usr/bin/env python3
"""Verify linked diagnostic labels, font, metadata, and register-save hooks."""
from pathlib import Path
import re
import struct
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1])
raw = (out / "arch/arm/boot/Image").read_bytes()
base = 0xc0008000
symbols = {}
for line in subprocess.check_output(["llvm-nm", "-n", str(out / "vmlinux")], text=True).splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)

def offset(name):
    off = symbols[name] - base
    assert 0 <= off < len(raw), name
    return off

assert raw[offset("a6_boot_seen"):offset("a6_boot_seen") + 4] == bytes(4)
font = (repo / "kernel/font8x8.bin").read_bytes()
assert len(font) == 2048
assert raw[offset("a6_boot_font"):offset("a6_boot_font") + len(font)] == font
labels = re.findall(r'\d+: \.asciz "([^"]+)"',
                    (repo / "boot/arm/linux-boot-status.S").read_text())
assert len(labels) == 24
for i, label in enumerate(labels):
    ptr = struct.unpack_from("<I", raw, offset("a6_boot_labels") + i * 4)[0] - base
    assert 0 <= ptr < len(raw)
    assert raw[ptr:ptr + len(label) + 1] == label.encode() + b"\0"
    assert len(label) <= 25
    assert 8 + len(label) * 24 <= 640
    assert 80 + i * 40 + 24 <= 1136
assert struct.unpack_from("<I", raw, offset("a6_fb_base_saved"))[0] == 0xbf7aa000
hooks = ["a6_stage_stack", "a6_stage_archin", "a6_arch_proc", "a6_arch_fdt",
         "a6_arch_memblock", "a6_arch_pagingin", "a6_page_prepare", "a6_arch_paging",
         "a6_stage_irqon", "a6_stage_rest", "a6_kinit_enter", "a6_kinit_basic",
         "a6_kinit_exec", "a6_userspace_syscall", "a6_fault_undef", "a6_fault_memory"]
hooks += ["a6_diag_" + s for s in ["mmu", "dwc_probe", "phy_probe", "phy_power",
                                  "phy_ready", "params", "udc", "serial"]]
assert len(hooks) == 24
if "a6_phy_labels" in symbols:
    for i in range(14):
        ptr = struct.unpack_from("<I", raw, offset("a6_phy_labels") + i * 4)[0] - base
        assert 0 <= ptr <= len(raw) - 26
        label = raw[ptr:ptr + 26]
        assert label.startswith(b"14 PHY ") and label[-1] == 0
        assert b"\0" not in label[:-1]
        hooks.append(f"a6_diag_phy_p{i}")
if "a6_diag_timer_row" in symbols:
    hooks.append("a6_diag_timer_row")
    observer = "a6_route_observe" if "a6_route_observe" in symbols else "a6_timer_observe"
    if "a6_line_observe" in symbols:
        observer = "a6_line_observe"
    # The AIC observer shares a translation unit with its clock accessor;
    # that accessor can be inlined and its out-of-line copy garbage-collected.
    for name in [observer]:
        assert name in symbols, name
if "a6_exec_hooks" in symbols:
    for name, addr in symbols.items():
        if name.startswith(("a6_exec_", "a6_elf_", "a6_user_", "a6_mm_", "a6_fault_")):
            # Data tables/labels are excluded; all callable late hooks must
            # survive ARM's pre-text NX permissions at free_initmem.
            if symbols["_text"] <= addr < symbols["_stext"]:
                raise AssertionError(f"late hook in NX head text: {name}")
    assert raw[offset("a6_exec_seen"):offset("a6_exec_seen") + 4] == bytes(4)
    for i in range(23):
        ptr = struct.unpack_from("<I", raw, offset("a6_exec_labels") + 4*i)[0] - base
        label = raw[ptr:ptr+26]
        assert label.startswith(f"E{i:02d} ".encode()) and len(label) == 26
        assert label[-1] == 0 and b"\0" not in label[:-1]
        fn = struct.unpack_from("<I", raw, offset("a6_exec_hooks") + 4*i)[0] & ~1
        matches = [name for name, addr in symbols.items() if (addr & ~1) == fn and name.startswith("a6_")]
        assert matches
        hooks.append(matches[0])
for name in hooks:
    start = offset(name)
    # Thumb PUSH.W all r0-r12 plus lr; the former BX LR stub must be gone.
    assert raw[start:start + 4] == bytes.fromhex("2de9ff5f"), name
    code = raw[start:start + 40]
    assert bytes.fromhex("73b6") in code, name  # CPSID if
    assert bytes.fromhex("bde8ff9f") in code, name  # POP.W r0-r12, pc
print(f"PASS: {len(hooks)} linked register-saving hooks, bounded labels, font and mapped metadata")

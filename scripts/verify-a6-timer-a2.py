#!/usr/bin/env python3
"""Check the corrected candidate against the prior passive timer diagnostic."""
from pathlib import Path
import subprocess
import sys
import struct
from a6_fdt import properties

out, dtb = map(Path, sys.argv[1:3])
full_speed = sys.argv[3:] == ["--full-speed"]
cpu0_only = sys.argv[3:] == ["--smp-cpu0-only"]
smp_bridge = sys.argv[3:] == ["--smp-bridge-quarantine"]
cpu1_tlbi_reservations = sys.argv[3:] == ["--cpu1-tlbi-reservations"]
cpu1_reservations = sys.argv[3:] == ["--cpu1-reservations"] or cpu1_tlbi_reservations
assert len(sys.argv) in (3, 4) and (len(sys.argv) == 3 or full_speed or cpu1_reservations or cpu0_only or smp_bridge)
repo = Path(__file__).resolve().parents[1]
old = (repo / "build/arm/a6-n42ap-usb-timer-trace.dtb").read_bytes()
new = dtb.read_bytes()

if smp_bridge:
    from a6_smp_bridge_fdt import strip_bridge_properties
    prior, current = properties(old), properties(new)
    strip_bridge_properties(current)
    current[("/timer", "interrupts")] = struct.pack(">I", 0xa3)
    assert prior == current, "unexpected bridge DT change"
elif cpu0_only:
    prior, current = properties(old), properties(new)
    key = ("/chosen", "bootargs")
    assert current[key] == prior[key][:-1] + b" maxcpus=1\0"
    current[key] = prior[key]
    assert current[("/timer", "interrupts")] == struct.pack(">I", 0xa2)
    current[("/timer", "interrupts")] = struct.pack(">I", 0xa3)
    assert prior == current, "unexpected CPU0-only SMP DT change"
elif cpu1_reservations:
    prior, current = properties(old), properties(new)
    node = "/reserved-memory/a6-cpu1-reset-vector@80000000"
    assert current.pop((node, "reg")) == struct.pack(">2I", 0x80000000, 0x2000)
    assert current.pop((node, "no-map")) == b""
    if cpu1_tlbi_reservations:
        node = "/reserved-memory/a6-cpu1-tlbi-private@83ff6000"
        assert current.pop((node, "reg")) == struct.pack(">2I", 0x83ff6000, 0x9000)
    else:
        node = "/reserved-memory/a6-cpu1-mailbox@83ffe000"
        assert current.pop((node, "reg")) == struct.pack(">2I", 0x83ffe000, 0x1000)
    assert current.pop((node, "no-map")) == b""
    assert current[("/timer", "interrupts")] == struct.pack(">I", 0xa2)
    current[("/timer", "interrupts")] = struct.pack(">I", 0xa3)
    assert prior == current, "unexpected DT change besides timer and CPU1 reservations"
else:
    assert len(old) == len(new)
    diffs = [(i, a, b) for i, (a, b) in enumerate(zip(old, new)) if a != b]
if full_speed:
    assert len(diffs) == 5 and diffs[0][1:] == (0xa3, 0xa2), diffs
    speed_offset = diffs[1][0]
    assert old[speed_offset:speed_offset + 10] == b"high-speed"
    assert new[speed_offset:speed_offset + 10] == b"full-speed"
    assert all(i in range(speed_offset, speed_offset + 10)
               for i, _, _ in diffs[1:]), diffs
elif not cpu1_reservations and not cpu0_only and not smp_bridge:
    assert len(diffs) == 1 and diffs[0][1:] == (0xa3, 0xa2), diffs
symbols = {}
for line in subprocess.check_output(["llvm-nm", "-n", str(out / "vmlinux")], text=True).splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
assert "a6_timer_observe" in symbols
if "a6_usb_diag" in symbols:
    if "a6_usb_report_sync" in symbols:
        assert "a6_usb_report_job" not in symbols
    else:
        assert "a6_usb_report_work" in symbols
        assert "a6_usb_report_job" in symbols
for name in ["a6_route_observe", "a6_line_observe", "route_active", "route_delivered"]:
    assert name not in symbols, name
raw = (out / "arch/arm/boot/Image").read_bytes()
if out.name == "linux-a6-usb-exec-prep":
    for i in range(41):
        prefix = f"K{i:02d} ".encode()
        pos = raw.find(prefix)
        assert pos >= 0, prefix
        assert raw[pos+25] == 0 and b"\0" not in raw[pos:pos+25], prefix
off = (symbols["a6_timer_irq_proof"] & ~1) - 0xc0008000
assert raw[off:off+2] == bytes.fromhex("7047"), "8th IRQ hook must remain BX LR"
print("PASS: DT differs only a3->a2" +
      (" and high-speed->full-speed" if full_speed else "") +
      (" and two checked CPU1 reservations" if cpu1_reservations else "") +
      (" and maxcpus=1 with no CPU1 node" if cpu0_only else "") +
      (" and checked CPU1 bridge/timer reservations" if smp_bridge else "") +
      "; passive observer present; active probes absent; IRQ hook returns")

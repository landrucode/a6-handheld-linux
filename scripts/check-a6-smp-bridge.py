#!/usr/bin/env python3
"""Accept only the isolated, pre-online quarantine profile for IMG3 packing."""
import hashlib
import json
import os
import re
import subprocess
import struct
import sys
from pathlib import Path

from a6_fdt import properties
from a6_smp_bridge_fdt import strip_bridge_properties

root, dtb = map(Path, sys.argv[1:])
scheduling = os.environ.get("A6_SMP_SCHEDULING") == "1"
line_probe = os.environ.get("A6_SMP_TIMER_LINE_PROBE") == "1"
if line_probe and scheduling:
    raise SystemExit("line observation must remain pre-RCU/offline")
expected_suffix = "smp-first-scheduling" if scheduling else ("smp-timer-line-checkpoint" if line_probe else "smp-bridge-quarantine")
if not root.name.endswith(expected_suffix) or not dtb.stem.endswith(expected_suffix):
    raise SystemExit("SMP output profile/paths mismatch")
repo = Path(__file__).resolve().parents[1]
config = (root / ".config").read_text()
for required in (
    "CONFIG_SMP=y", "CONFIG_NR_CPUS=2", "CONFIG_GENERIC_IRQ_IPI_MUX=y",
    "# CONFIG_HOTPLUG_CPU is not set", "# CONFIG_CPU_IDLE is not set",
    "# CONFIG_PERF_EVENTS is not set", "CONFIG_CMDLINE_FORCE=y",
):
    if required not in config.splitlines():
        raise SystemExit(f"missing bridge config: {required}")
cmdline = re.search(r'^CONFIG_CMDLINE="(.*)"$', config, re.M)
wifi_cpu0_control = (scheduling and os.environ.get('A6_WIFI_NATIVE') == '1' and
                     os.environ.get('A6_WIFI_BOOT_CPUS') == '1')
expected_cap = 'maxcpus=1' if wifi_cpu0_control else 'maxcpus=2'
if not cmdline or expected_cap not in cmdline.group(1).split():
    raise SystemExit('bridge needs explicit CPU cap: ' + expected_cap)
if not wifi_cpu0_control and "maxcpus=1" in cmdline.group(1).split():
    raise SystemExit("bridge capped to CPU0")
baseline = repo / "build/arm/a6-n42ap-low-battery-boot-defaults.dtb"
prior, current = properties(baseline.read_bytes()), properties(dtb.read_bytes())
strip_bridge_properties(current)
if os.environ.get('A6_RAM_MIB', '768') == '944':
    memory = ('/memory@80000000', 'reg')
    if (os.environ.get('A6_BROWSER_SANDBOX') != '1' or
            'vmalloc=64M' not in cmdline.group(1).split() or
            '# CONFIG_HIGHMEM is not set' not in config.splitlines() or
            prior[memory] != struct.pack('>II', 0x80000000, 768*1024*1024) or
            current[memory] != struct.pack('>II', 0x80000000, 944*1024*1024)):
        raise SystemExit('944MiB diagnostic geometry/config mismatch')
    # Compare every remaining property exactly with the retained bridge DT.
    current[memory] = prior[memory]
if prior != current:
    changes = sorted(key for key in set(prior) | set(current)
                     if prior.get(key) != current.get(key))
    raise SystemExit(f"unexpected final bridge DT changes: {changes}")

folder = root / "a6-smp-bridge-audit"
folder.mkdir(exist_ok=True)


def disassemble(relative):
    raw = subprocess.check_output(["llvm-objdump", "-dr", str(root / relative)], text=True)
    (folder / (Path(relative).name + ".txt")).write_text(raw)
    return raw


def require(text, *symbols):
    for symbol in symbols:
        if symbol not in text:
            raise SystemExit(f"compiled bridge lacks {symbol}")


head = disassemble("arch/arm/kernel/head.o")
if head.count("a6_smp_secondary_data") != 4:
    raise SystemExit("both physical and virtual head.S handoffs must use immutable shadow")
smp = disassemble("arch/arm/kernel/smp.o")
require(smp, "a6_smp_secondary_checkpoint")
secondary = smp.split("<secondary_start_kernel>:", 1)[1]
if secondary.index("a6_smp_secondary_checkpoint") > secondary.index("notify_cpu_starting"):
    raise SystemExit("quarantine occurs after RCU/startup participation")
bridge = disassemble("drivers/irqchip/a6-smp.o")
require(bridge, "a6_smp_boot_secondary", "a6_smp_secondary_checkpoint",
        "v7_flush_kern_dcache_area", "wfe", "a6_smp_awake_idle")
checkpoint = bridge.split("<a6_smp_secondary_checkpoint>:", 1)[1]
checkpoint = re.split(r"\n[0-9a-f]+ <", checkpoint, maxsplit=1)[0]
if "wfe" not in checkpoint or (not scheduling and re.search(r"\b(?:bx\s+lr|pop[^\n]*pc)\b", checkpoint)):
    raise SystemExit("pre-online checkpoint must park without returning")
timer = disassemble("drivers/clocksource/timer-apple-a6.o")
require(timer, "a6_cpu1_timer_starting", "a6_cpu1_timer_interrupt",
        "irq_force_affinity", "enable_irq", "__cpuhp_setup_state",
        "clockevents_config_and_register", "a6_smp_timer_ready")
aic = disassemble("drivers/irqchip/irq-apple-a6-aic.o")
require(aic, "a6_smp_aic_set_affinity", "a6_aic_starting_cpu", "ipi_mux_process")
affinity = aic.split("<a6_smp_aic_set_affinity>:", 1)[1]
affinity = re.split(r"\n[0-9a-f]+ <", affinity, maxsplit=1)[0]
if not re.search(r"\bcmp[^\n]*#0xa5\b", affinity):
    raise SystemExit("compiled CPU1 affinity guard lacks measured timer IRQ 0xa5")
stub = disassemble("a6-smp-secondary.o")
if re.search(r"\bwfi\b", stub) or re.search(r"mcr[^\n]*c12", stub):
    raise SystemExit("bridge contains WFI or unavailable VBAR access")
if "a6_smp_bridge_exception" not in stub or "a6_smp_bridge_park" not in stub:
    raise SystemExit("bridge lacks resident exception/park targets")
subprocess.run([sys.executable, str(repo / "scripts/check-a6-smp-local-tlbi.py"),
                str(root), str(folder / "local-tlbi")], check=True)
subprocess.run([sys.executable, str(repo / "scripts/a6-smp-secondary-entry.py"),
                str(root)], check=True)
if scheduling:
    require(bridge, "a6_probe_work_fn", "a6_probe_store", "smp_call_function_single_async",
            "wait_for_completion_timeout", "apply_to_page_range",
            "flush_tlb_kernel_range", "flush_tlb_all")
    if "a6_smp_timer_checkpoint_start" in checkpoint:
        raise SystemExit("scheduling must use normal timer startup callback")
if line_probe:
    require(checkpoint, "a6_smp_timer_line_probe")
    require(timer, "a6_smp_aic_timer_snapshot")
result = {"profile": expected_suffix, "cpu1_may_be_online": scheduling and not wifi_cpu0_control,
          "boot_cpu_cap": 1 if wifi_cpu0_control else 2}
for name, path in (
    ("zimage", root / "arch/arm/boot/zImage"), ("dtb", dtb),
    ("vmlinux", root / "vmlinux"), ("config", root / ".config"),
    ("stub", root / "a6-smp-secondary.bin"),
):
    result[name + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
(root / "a6-smp-bridge-verified.json").write_text(json.dumps(result, indent=2) + "\n")
print("PASS bridge: immutable handoff, markers, early timer, local TLB/IPI; " +
      ("Wi-Fi control boot capped to CPU0" if wifi_cpu0_control else
       "normal online continuation + kernel proof" if scheduling else "pre-online park"))

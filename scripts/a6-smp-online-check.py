#!/usr/bin/env python3
"""Gate the first scheduling boot on timers, call-function IPIs and shootdowns."""
import importlib.util
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bridge_capture", ROOT / "scripts/a6-smp-bridge-check.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def require(raw, pattern, path):
    return bridge.require(raw, pattern, path)


def main():
    folder = ROOT / "logs/smp"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    first = folder / f"{stamp}-smp-online-first.console.txt"
    second = folder / f"{stamp}-smp-online-second.console.txt"
    before = bridge.snapshot(first, "online-first")
    require(before, r"^A6_CPU_ONLINE=0-1$", first)
    require(before, r"^A6_SMP_BRIDGE_V1 .*result=0 quarantine=0 stage=6\b", first)
    require(before, r"^A6_SMP_TIMER_V1 kind=local registration=early_time_init checkpoint=normal_starting prepared=1 ready=1 start_result=0\b", first)
    time.sleep(5)
    after = bridge.snapshot(second, "online-second")
    require(after, r"^A6_CPU_ONLINE=0-1$", second)
    require(after, r"^auto=1 paused=0 fault=0 attached=1\b", second)
    require(after, r"^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 .*threshold_mv=3600\b", second)
    timer = r"^A6_SMP_TIMER_V1 .*\birqs=(\d+)$"
    cpu1_before = int(require(before, timer, first).group(1))
    cpu1_after = int(require(after, timer, second).group(1))
    cpu0_before = bridge.timer_count(before, first)
    cpu0_after = bridge.timer_count(after, second)
    if cpu0_after <= cpu0_before or cpu1_after <= cpu1_before:
        raise RuntimeError("per-core timer count did not advance; stop before probe/stress")
    row = require(after, r"(?m)^\s*\d+:\s*(\d+)\s+(\d+)\s+.*apple-a6-timer-cpu1$", second)
    if int(row.group(1)) or not int(row.group(2)):
        raise RuntimeError("CPU1 timer IRQ did not arrive exclusively on CPU1")
    captures = []
    output = folder / f"{stamp}-smp-shootdown.console.txt"
    commands = ["echo prove > /sys/firmware/a6_smp_bridge/probe"]
    started = False
    for iteration in range(65):
        command = commands[0] if not started else "cat /sys/firmware/a6_smp_bridge/probe_status"
        run = subprocess.run([sys.executable, str(bridge.HELPER),
                              command + "; echo A6_ONLINE_PROBE_END", "--until",
                              "A6_ONLINE_PROBE_END", "--timeout", "10"],
                             capture_output=True, text=True, timeout=20)
        raw = run.stdout + run.stderr
        captures.append(raw)
        output.write_text("\n".join(captures))
        if run.returncode:
            raise RuntimeError(f"probe capture failed: {output}")
        if not started:
            if "write error" in raw or "can't create" in raw:
                raise RuntimeError(f"probe refused: {output}")
            started = True
        else:
            match = re.search(r"A6_SMP_SHOOTDOWN_V1 attempted=1 phase=(\d+) result=(-?\d+) calls=(\d+) controls=(\d+) ranges=(\d+) full=(\d+)", raw)
            if match and match.group(1) in ("3", "4"):
                if match.groups()[0:2] != ("3", "0") or match.group(3, 4, 5, 6) != ("97", "32", "16", "16"):
                    raise RuntimeError(f"shootdown/control failed: {match.group(0)}; {output}")
                break
        time.sleep(1)
    else:
        raise RuntimeError(f"probe did not finish within bound: {output}")
    result = {"result": "pass", "online": "0-1", "timer_cpu0": [cpu0_before, cpu0_after],
              "timer_cpu1": [cpu1_before, cpu1_after], "controls": 32,
              "range_flushes": 16, "full_flushes": 16, "ipi_calls": int(match.group(3)),
              "captures": [str(p.relative_to(ROOT)) for p in (first, second, output)]}
    target = folder / f"{stamp}-smp-online.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS two CPUs, local timers, Linux call-function IPI and controlled shootdowns: {target}")


if __name__ == "__main__":
    main()

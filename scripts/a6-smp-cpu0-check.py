#!/usr/bin/env python3
"""Bounded host-side acceptance check for the SMP-configured CPU0-only RAM boot."""
import json
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/a6-usb-acm-direct.py"


def snapshot(path: Path, name: str) -> str:
    marker = "A6_SMP_CPU0_" + uuid.uuid4().hex[:12]
    command = (
        "uname -a; "
        "printf 'A6_CPU_ONLINE='; cat /sys/devices/system/cpu/online; "
        "printf 'A6_CPU_POSSIBLE='; cat /sys/devices/system/cpu/possible; "
        "printf 'A6_CMDLINE='; cat /proc/cmdline; "
        "printf 'A6_TIMER_IRQ='; grep apple-a6-timer /proc/interrupts; "
        "cat /sys/firmware/a6_charger_policy/status; "
        "cat /sys/firmware/a6_charger_policy/low_battery_status; "
        f"echo {marker}"
    )
    # USB ACM appears slightly after the gadget enumerates. Allow that boot
    # race, but retain every failed capture if the phone never becomes ready.
    attempts = []
    for _ in range(10):
        run = subprocess.run(
            [sys.executable, str(HELPER), command, "--until", marker,
             "--timeout", "20"], capture_output=True, text=True,
        )
        raw = run.stdout + run.stderr
        attempts.append(raw)
        if run.returncode == 0 and marker in raw:
            path.write_text(raw)
            return raw.replace("\r", "")
        time.sleep(1)
    path.write_text("\n--- retry ---\n".join(attempts))
    raise RuntimeError(f"{name} capture incomplete: {path}")


def require(raw: str, pattern: str, path: Path) -> re.Match[str]:
    match = re.search(pattern, raw, re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing or invalid {pattern!r}: {path}")
    return match


def timer_count(raw: str, path: Path) -> int:
    return int(require(raw, r"^A6_TIMER_IRQ=\s*\d+:\s*(\d+)\s+", path).group(1))


def main() -> None:
    folder = ROOT / "logs/smp"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    first = folder / f"{stamp}-smp-cpu0-first.console.txt"
    second = folder / f"{stamp}-smp-cpu0-second.console.txt"
    before = snapshot(first, "first")
    require(before, r"^A6_CPU_ONLINE=0$", first)
    possible = require(before, r"^A6_CPU_POSSIBLE=([0-9,-]+)$", first).group(1)
    require(before, r"^A6_CMDLINE=.*\bmaxcpus=1\b", first)
    require(before, r"^auto=1 paused=0 fault=0 attached=1\b", first)
    require(before, r"^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 .*threshold_mv=3600\b", first)
    start_irq = timer_count(before, first)
    time.sleep(5)
    after = snapshot(second, "second")
    end_irq = timer_count(after, second)
    if end_irq <= start_irq:
        raise RuntimeError(f"timer IRQ did not advance: {start_irq} -> {end_irq}; {second}")
    result = {
        "result": "pass", "online": "0", "possible": possible,
        "maxcpus": 1, "timer_irq_before": start_irq,
        "timer_irq_after": end_irq,
        "first": str(first.relative_to(ROOT)),
        "second": str(second.relative_to(ROOT)),
    }
    target = folder / f"{stamp}-smp-cpu0.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS SMP-configured CPU0-only boot; timer IRQ {start_irq}->{end_irq}; {target}")


if __name__ == "__main__":
    main()

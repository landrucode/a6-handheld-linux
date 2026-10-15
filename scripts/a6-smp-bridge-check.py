#!/usr/bin/env python3
"""Bounded host-side acceptance check for the SMP-configured pre-online CPU1 checkpoint RAM boot."""
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
    marker = "A6_SMP_BRIDGE_" + uuid.uuid4().hex[:12]
    commands = [
        "uname -a",
        "cat /sys/firmware/a6_smp_bridge/status",
        "cat /sys/firmware/a6_smp_bridge/timer",
        "dmesg | grep -E 'A6 SMP|A6 timer|CPU1|failed to boot'",
        "printf 'A6_CPU_ONLINE='; cat /sys/devices/system/cpu/online",
        "printf 'A6_CPU_POSSIBLE='; cat /sys/devices/system/cpu/possible",
        "printf 'A6_CMDLINE='; cat /proc/cmdline",
        "printf 'A6_TIMER_IRQ='; grep apple-a6-timer /proc/interrupts",
        "cat /sys/firmware/a6_charger_policy/status",
        "cat /sys/firmware/a6_charger_policy/low_battery_status",
    ]
    captures = []
    for index, command in enumerate(commands):
        end = marker + "_" + str(index)
        attempts = 10 if index == 0 else 1
        for attempt in range(attempts):
            run = subprocess.run(
                [sys.executable, str(HELPER), command + "; echo " + end,
                 "--until", end, "--timeout", "20"],
                capture_output=True, text=True, timeout=30,
            )
            raw = run.stdout + run.stderr
            captures.append(raw)
            path.write_text("\n".join(captures))
            if run.returncode == 0 and re.search(
                    rf"(?:^|\r?\n){re.escape(end)}(?:\r?\n|$)", raw):
                break
            if attempt + 1 == attempts:
                raise RuntimeError(f"{name} capture incomplete: {path}")
            time.sleep(1)
    return "\n".join(captures).replace("\r", "")


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
    first = folder / f"{stamp}-smp-bridge-first.console.txt"
    second = folder / f"{stamp}-smp-bridge-second.console.txt"
    before = snapshot(first, "first")
    require(before, r"^A6_CPU_ONLINE=0$", first)
    possible = require(before, r"^A6_CPU_POSSIBLE=([0-9,-]+)$", first).group(1)
    require(before, r"^A6_CMDLINE=.*\bmaxcpus=2\b", first)
    require(before, r"^A6_SMP_BRIDGE_V1 .*result=0 quarantine=1 stage=5\b", first)
    require(before, r"^A6_SMP_TIMER_V1 kind=local registration=early_time_init checkpoint=explicit_before_rcu prepared=1 ready=1 start_result=0 .* irqs=0$", first)
    require(before, r"checkpoint_result=0\b", first)
    cpsr = int(require(before, r"parked_cpsr=([0-9a-f]+)", first).group(1), 16)
    ctl = int(require(before, r"timer_ctl=([0-9a-f]+)", first).group(1), 16)
    if cpsr & 0xc0 != 0xc0 or ctl & 3 != 2:
        raise RuntimeError("CPU1 interrupts or local timer not masked")
    for index in range(5):
        words = require(before, rf"^handoff_word{index}=([0-9a-f]+)/(\w+)$", first)
        if words.group(1) != words.group(2):
            raise RuntimeError(f"handoff word {index} differs")
    if possible != "0-1":
        raise RuntimeError(f"CPU1 not possible: {possible}")
    require(before, r"^auto=1 paused=0 fault=0 attached=1\b", first)
    require(before, r"^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 .*threshold_mv=3600\b", first)
    start_irq = timer_count(before, first)
    time.sleep(5)
    after = snapshot(second, "second")
    require(after, r"^A6_CPU_ONLINE=0$", second)
    require(after, r"^auto=1 paused=0 fault=0 attached=1\b", second)
    require(after, r"^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 .*threshold_mv=3600\b", second)
    end_irq = timer_count(after, second)
    if end_irq <= start_irq:
        raise RuntimeError(f"timer IRQ did not advance: {start_irq} -> {end_irq}; {second}")
    result = {
        "result": "pass", "online": "0", "possible": possible,
        "maxcpus": 2, "timer_irq_before": start_irq,
        "timer_irq_after": end_irq,
        "first": str(first.relative_to(ROOT)),
        "second": str(second.relative_to(ROOT)),
    }
    target = folder / f"{stamp}-smp-bridge.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS SMP-configured pre-online CPU1 checkpoint boot; timer IRQ {start_irq}->{end_irq}; {target}")


if __name__ == "__main__":
    main()

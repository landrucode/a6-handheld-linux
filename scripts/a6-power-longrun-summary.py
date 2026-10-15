#!/usr/bin/env python3
"""Summarize the 30-second snapshots in an A6 RAM power journal."""

import argparse
from pathlib import Path
import re


def fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"\b([a-z][a-z0-9_]*)=(-?\w+)", line))


def read_snapshots(path: Path) -> list[dict]:
    chunks = path.read_text().split("\nA6_POWER_SAMPLE=")[1:]
    snapshots = []
    for chunk in chunks:
        sample_match = re.match(r"(\d+) uptime=([\d.]+)", chunk)
        if not sample_match:
            continue
        lines = chunk.splitlines()
        policy = next((line for line in lines if line.startswith("A6_D1972_500_CLASS_CANDIDATE_V5 ")), "")
        auto = next((line for line in lines if line.startswith("auto=")), "")
        voltage = next((line for line in lines if line.startswith("vbus_mv=")), "")
        low = next((line for line in lines if line.startswith("A6_LOW_BATTERY_CANDIDATE_V3 ")), "")
        if not all((policy, auto, voltage, low)):
            continue
        snapshots.append({
            "sample": int(sample_match.group(1)),
            "uptime": float(sample_match.group(2)),
            **fields(policy), **fields(auto), **fields(voltage),
            "low": fields(low),
        })
    return snapshots


def summarize(snapshots: list[dict]) -> None:
    if not snapshots:
        raise SystemExit("No complete power snapshots found")
    first, last = snapshots[0], snapshots[-1]
    print(f"snapshots={len(snapshots)} uptime={first['uptime']:.0f}..{last['uptime']:.0f}s "
          f"duration={(last['uptime'] - first['uptime']) / 60:.1f}min")
    for label, subset in (
        ("attached", [s for s in snapshots if s.get("attached") == "1"]),
        ("detached", [s for s in snapshots if s.get("attached") == "0"]),
        ("charging", [s for s in snapshots if s.get("active") == "1"]),
        ("thermal_hold", [s for s in snapshots if s.get("thermal_hold") == "1"]),
        ("fault", [s for s in snapshots if s.get("fault") == "1"]),
    ):
        if subset:
            voltages = [int(s["vbat_mv"]) for s in subset]
            temps = [int(s["tbat_c_candidate"]) for s in subset]
            print(f"{label}: n={len(subset)} VBAT={voltages[0]}..{voltages[-1]}mV "
                  f"range={min(voltages)}..{max(voltages)}mV "
                  f"TBAT={min(temps)}..{max(temps)}C")
        else:
            print(f"{label}: n=0")
    previous = None
    for s in snapshots:
        state = tuple(s.get(key) for key in
                      ("attached", "active", "held", "thermal_hold", "fault", "auto_arms"))
        if state != previous:
            print(f"event sample={s['sample']} uptime={s['uptime']:.0f}s "
                  f"attached={s.get('attached')} active={s.get('active')} "
                  f"held={s.get('held')} thermal={s.get('thermal_hold')} "
                  f"fault={s.get('fault')} arms={s.get('auto_arms')} "
                  f"VBAT={s.get('vbat_mv')}mV VBUS={s.get('vbus_mv')}mV")
            previous = state
    print("last_low_battery_status:", " ".join(
        f"{key}={value}" for key, value in last["low"].items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    summarize(read_snapshots(parser.parse_args().journal))

#!/usr/bin/env python3
"""Collect bounded A6 battery-voltage samples from the guarded USB shell."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time


def read_sample(helper: Path) -> dict:
    command = (
        "echo sample-vbat-and-restore > /sys/firmware/a6_vbat_adc/sample; "
        "echo SAMPLE_EXIT=$?; cat /sys/firmware/a6_vbat_adc/status; "
        "cat /sys/class/power_supply/a6-d1972-battery/voltage_now\n"
    )
    result = subprocess.run(
        [str(helper), command], capture_output=True, text=True, timeout=10
    )
    output = result.stdout + result.stderr
    if result.returncode:
        raise RuntimeError(f"USB helper exited {result.returncode}: {output[-400:]}")
    def field(name: str) -> int:
        match = re.search(rf"\b{name}=(-?\d+)\b", output)
        if not match:
            raise RuntimeError(f"missing {name}: {output[-400:]}")
        return int(match.group(1))
    if "A6_D1972_VBAT_ADC_V1" not in output:
        raise RuntimeError(f"wrong image or missing status: {output[-400:]}")
    voltage = re.search(r"(?m)^([0-9]{7})\s*$", output)
    if not voltage:
        raise RuntimeError(f"missing cached battery voltage: {output[-400:]}")
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "sample_exit": field("SAMPLE_EXIT"),
        "result": field("result"),
        "cleanup_result": field("cleanup_result"),
        "restored": field("restored"),
        "samples": field("samples"),
        "raw": field("raw"),
        "voltage_uv": int(voltage.group(1)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--interval", type=int, default=65)
    parser.add_argument("--stop-below-uv", type=int, default=3600000)
    parser.add_argument("--helper", type=Path, default=Path("/tmp/a6_usb_acm"))
    parser.add_argument("--output", type=Path, help="append JSON lines to this file")
    args = parser.parse_args()
    if not 1 <= args.count <= 20 or not 60 <= args.interval <= 3600:
        parser.error("count must be 1..20 and interval 60..3600 seconds")
    if not args.helper.is_file():
        parser.error("USB helper missing")
    def emit(record: dict) -> None:
        line = json.dumps(record, sort_keys=True)
        print(line, flush=True)
        if args.output:
            with args.output.open("a") as handle:
                handle.write(line + "\n")
    for _ in range(args.count):
        time.sleep(args.interval)
        try:
            sample = read_sample(args.helper)
        except Exception as exc:
            emit({"error": str(exc)})
            break
        emit(sample)
        if (sample["sample_exit"] or sample["result"] or
                sample["cleanup_result"] or sample["restored"] != 1 or
                sample["voltage_uv"] < args.stop_below_uv):
            break


if __name__ == "__main__":
    main()

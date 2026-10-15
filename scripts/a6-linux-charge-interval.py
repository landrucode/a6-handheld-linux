#!/usr/bin/env python3
"""Log guarded VBAT samples during a USB-connected Linux capacity trial."""
import argparse
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/a6-usb-acm-direct.py"
END = "END_CHARGE_INTERVAL_SAMPLE"
COMMAND = ("echo sample-vbat-and-restore > /sys/firmware/a6_vbat_adc/sample; "
           "echo sample_rc=$?; cat /sys/firmware/a6_vbat_adc/status; "
           "cat /proc/uptime; echo " + END)


def sample():
    result = subprocess.run(
        ["python3", str(HELPER), COMMAND, "--until", END, "--timeout", "20"],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
    output = result.stdout
    def field(pattern):
        match = re.search(pattern, output)
        if not match:
            raise RuntimeError(f"missing {pattern}: {output[-500:]}")
        return int(match.group(1))
    record = {
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sample_rc": field(r"sample_rc=(\d+)"),
        "result": field(r"result=(-?\d+)"),
        "cleanup_result": field(r"cleanup_result=(-?\d+)"),
        "restored": field(r"restored=(\d+)"),
        "raw": field(r"raw=(\d+)"),
        "vbat_mv": field(r"vbat_candidate_mv=(\d+)"),
        "samples": field(r"samples=(\d+)"),
    }
    uptime = re.search(r"(?m)^(\d+\.\d+)\s+\d+\.\d+\s*$", output)
    if uptime:
        record["uptime_s"] = float(uptime.group(1))
    if record["sample_rc"] or record["result"] or record["cleanup_result"] or not record["restored"]:
        raise RuntimeError(f"guarded ADC failed: {record}")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=3600, help="seconds; default 3600")
    parser.add_argument("--interval", type=int, default=300, help="seconds; default 300")
    parser.add_argument("--stop-mv", type=int, default=3600,
                        help="stop monitoring below this guarded VBAT reading")
    args = parser.parse_args()
    if args.duration < 60 or args.interval < 65 or not 3300 <= args.stop_mv <= 4000:
        parser.error("duration >=60 s, interval >=65 s, and stop-mv 3300..4000 required")
    out = ROOT / "build/session-logs" / ("linux-charge-interval-" +
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    next_at = start + min(args.interval, args.duration)
    print(f"logging {out}", flush=True)
    while next_at <= start + args.duration + 0.1:
        time.sleep(max(0, next_at - time.monotonic()))
        record = sample()
        with out.open("a") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        print(json.dumps(record, sort_keys=True), flush=True)
        if record["vbat_mv"] < args.stop_mv:
            print(f"VBAT below {args.stop_mv} mV; monitoring stopped. "
                  "Phone shutdown is NOT automatic.", flush=True)
            raise SystemExit(2)
        next_at += args.interval

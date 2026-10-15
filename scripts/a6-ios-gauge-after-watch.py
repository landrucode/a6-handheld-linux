#!/usr/bin/env python3
"""Timestamp the Linux USB exit and capture the next accessible iOS gauge."""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYS_USB = Path("/sys/bus/usb/devices")
OUT = ROOT / "build/session-logs/ios-gauge"


def now():
    return dt.datetime.now(dt.timezone.utc)


def usb_ids():
    found = set()
    for vendor in SYS_USB.glob("*/idVendor"):
        try:
            product = vendor.with_name("idProduct").read_text().strip().lower()
            found.add((vendor.read_text().strip().lower(), product))
        except OSError:
            continue
    return found


def save(path, report):
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default="UNIX:/tmp/a6muxd")
    parser.add_argument("--poll", type=int, default=10)
    parser.add_argument("--timeout-hours", type=float, default=12)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--linux-start")
    args = parser.parse_args()
    if args.poll < 2 or args.timeout_hours <= 0:
        parser.error("poll must be >=2 seconds and timeout-hours positive")
    if bool(args.baseline) != bool(args.linux_start):
        parser.error("--baseline and --linux-start must be supplied together")
    if args.baseline and not args.baseline.is_file():
        parser.error("baseline JSON does not exist")
    if args.baseline:
        args.baseline = args.baseline.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (now().strftime("%Y%m%dT%H%M%SZ") + "-linux-exit-watch.json")
    report = {"started_utc": now().isoformat(), "linux_end_utc": None,
              "after_snapshot": None, "comparison": None}
    save(path, report)
    deadline = time.monotonic() + args.timeout_hours * 3600
    absent_since = None
    next_attempt = 0
    while time.monotonic() < deadline:
        ids = usb_ids()
        gadget = ("0525", "a4aa") in ids
        if gadget:
            absent_since = None
            if report["linux_end_utc"] is not None:
                report["linux_end_utc"] = None
                save(path, report)
                print("Linux gadget returned; cleared exit timestamp", flush=True)
        elif absent_since is None:
            absent_since = now()
        elif report["linux_end_utc"] is None and (now() - absent_since).total_seconds() >= args.poll:
            report["linux_end_utc"] = absent_since.isoformat()
            save(path, report)
            print(f"Linux gadget absent since {report['linux_end_utc']}", flush=True)
        # This host has permanent Apple keyboard/Bluetooth devices. Wait for
        # the iPhone's iOS USB identity, not any Apple USB device.
        if report["linux_end_utc"] and ("05ac", "12a8") in ids:
            if time.monotonic() >= next_attempt:
                env = os.environ.copy()
                env["USBMUXD_SOCKET_ADDRESS"] = args.socket
                try:
                    done = subprocess.run(
                        [sys.executable, str(ROOT / "scripts/a6-ios-gauge-snapshot.py"),
                         "after-linux"], cwd=ROOT, env=env, capture_output=True,
                        text=True, timeout=120, check=False)
                except subprocess.TimeoutExpired:
                    print("iOS snapshot timed out; will retry", flush=True)
                else:
                    if done.returncode == 0:
                        report["after_snapshot"] = done.stdout.splitlines()[0]
                        if args.baseline:
                            compared = subprocess.run(
                                [sys.executable,
                                 str(ROOT / "scripts/a6-ios-gauge-compare.py"),
                                 str(args.baseline), report["after_snapshot"],
                                 "--linux-start", args.linux_start,
                                 "--linux-end", report["linux_end_utc"]],
                                cwd=ROOT, capture_output=True, text=True,
                                timeout=30, check=False)
                            report["comparison"] = (compared.stdout if
                                compared.returncode == 0 else compared.stderr)
                        save(path, report)
                        print(done.stdout, flush=True)
                        if report["comparison"]:
                            print(report["comparison"], flush=True)
                        print(f"exit metadata: {path}", flush=True)
                        return 0
                    print(f"iOS snapshot unavailable ({done.returncode}); will retry",
                          flush=True)
                next_attempt = time.monotonic() + 60
        time.sleep(args.poll)
    report["timed_out_utc"] = now().isoformat()
    save(path, report)
    print(f"watch timed out; metadata: {path}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Collect host and phone evidence for one attended kernel VBUS reconnect."""

from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def gadget_device() -> str | None:
    for entry in Path("/sys/bus/usb/devices").iterdir():
        try:
            if (entry / "idVendor").read_text().strip() == "0525" and \
               (entry / "idProduct").read_text().strip() == "a4aa":
                return f"{entry.name}:{(entry / 'devnum').read_text().strip()}"
        except (OSError, ValueError):
            continue
    return None


def phone(command: str, marker: str) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/a6-usb-acm-direct.py"),
         command, "--until", marker, "--timeout", "20"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode or not re.search(
        rf"(?:^|\r?\n){re.escape(marker)}(?:\r?\n|$)", result.stdout
    ):
        raise RuntimeError(f"phone capture failed: {result.stderr[-300:]} "
                           f"{result.stdout[-300:]}")
    return result.stdout


def main() -> None:
    initial = gadget_device()
    if initial is None:
        raise SystemExit("Linux gadget must be connected before collection starts")
    started = datetime.now(timezone.utc)
    print(f"Watching for a new Linux gadget after {initial}; perform one cable cycle now", flush=True)
    deadline = time.monotonic() + 900
    new = None
    capture = ""
    interrupted = False
    try:
        while time.monotonic() < deadline:
            time.sleep(1)
            candidate = gadget_device()
            if candidate is None or candidate == initial:
                continue
            try:
                capture = phone(
                    "echo A6_VBUS_CAPTURE_BEGIN; "
                    "cat /sys/firmware/a6_charger_policy/status; "
                    "cat /sys/firmware/a6_charger_policy/low_battery_status; "
                    "dmesg | tail -n 180; echo A6_VBUS_CAPTURE_END",
                    "A6_VBUS_CAPTURE_END",
                )
            except (RuntimeError, subprocess.TimeoutExpired):
                continue
            new = candidate
            break
    except KeyboardInterrupt:
        interrupted = True
    finally:
        host = subprocess.run(
            ["journalctl", "-k", "--since",
             started.strftime("%Y-%m-%d %H:%M:%S UTC"), "--no-pager"],
            capture_output=True, text=True, check=False,
        )
        counts = {code: len(re.findall(rf"error {code}\b", host.stdout))
                  for code in ("-110", "-71", "-62")}
        folder = ROOT / "logs/usb"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{started:%Y%m%dT%H%M%SZ}-kernel-vbus-trial.txt"
        with path.open("x", encoding="utf-8") as file:
            file.write(f"started_utc={started.isoformat()}\n"
                       f"initial_device={initial}\nnew_device={new}\n"
                       f"interrupted={int(interrupted)}\n"
                       f"journalctl_exit={host.returncode}\n"
                       f"host_errors=-110:{counts['-110']} -71:{counts['-71']} "
                       f"-62:{counts['-62']}\n\n"
                       f"HOST KERNEL LOG\n{host.stdout}\n"
                       f"HOST ERRORS\n{host.stderr}\n"
                       f"PHONE CAPTURE\n{capture}\n")
        print(f"Saved {path}")
    if interrupted:
        raise SystemExit(130)
    if not new:
        raise SystemExit("No returning Linux shell within fifteen minutes")
    print(f"Linux shell returned as {new}")


if __name__ == "__main__":
    main()

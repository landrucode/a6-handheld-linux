#!/usr/bin/env python3
"""Wait for the A6 gadget after a wall-source transfer and save RAM evidence."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def gadget_present() -> bool:
    for device in Path("/sys/bus/usb/devices").iterdir():
        try:
            if (device / "idVendor").read_text().strip() == "0525" and \
               (device / "idProduct").read_text().strip() == "a4aa":
                return True
        except OSError:
            continue
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=45)
    args = parser.parse_args()
    if not 1 <= args.minutes <= 120:
        parser.error("--minutes must be between 1 and 120")
    if gadget_present():
        parser.error("start after the phone has left the laptop")

    started = datetime.now(timezone.utc)
    deadline = time.monotonic() + args.minutes * 60
    collected = False
    power_output = ""
    power_error = ""
    interrupted = False
    print(f"Waiting for A6 USB return since {started.isoformat()}", flush=True)
    try:
        while time.monotonic() < deadline:
            if gadget_present():
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/a6-phone-power-log.py"),
                     "collect"], capture_output=True, text=True,
                    timeout=150, check=False,
                )
                power_output = result.stdout
                power_error = result.stderr
                if result.returncode == 0:
                    collected = True
                    print(power_output.strip(), flush=True)
                    break
            time.sleep(2)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        host = subprocess.run(
            ["journalctl", "-k", "--since",
             started.strftime("%Y-%m-%d %H:%M:%S UTC"), "--no-pager"],
            capture_output=True, text=True, check=False,
        )
        usb_lines = [line for line in host.stdout.splitlines()
                     if "usb 1-5" in line or "cdc_acm 1-5" in line]
        folder = ROOT / "logs/usb"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{started:%Y%m%dT%H%M%SZ}-wall-return.txt"
        path.write_text(
            f"started_utc={started.isoformat()}\n"
            f"ended_utc={datetime.now(timezone.utc).isoformat()}\n"
            f"collected={int(collected)} interrupted={int(interrupted)}\n"
            f"journalctl_exit={host.returncode}\n"
            f"power_output={power_output.strip()}\n"
            f"power_error={power_error.strip()}\n\n"
            "HOST USB LOG\n" + "\n".join(usb_lines) + "\n"
        )
        print(f"Saved host return log: {path}", flush=True)
    if interrupted:
        return 130
    return 0 if collected else 1


if __name__ == "__main__":
    raise SystemExit(main())

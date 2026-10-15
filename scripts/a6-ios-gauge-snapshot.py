#!/usr/bin/env python3
"""Capture read-only iOS gas-gauge diagnostics for a Linux charging A/B test."""
import argparse
import datetime as dt
import json
import plistlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/session-logs/ios-gauge"


def run(command):
    done = subprocess.run(command, capture_output=True, timeout=30, check=False)
    if done.returncode:
        raise SystemExit(f"{' '.join(command)} failed ({done.returncode}): "
                         + done.stderr.decode(errors="replace").strip())
    if b"<plist" not in done.stdout:
        raise SystemExit(f"{' '.join(command)} did not return a plist")
    return done.stdout


def flatten(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, value


def capture(label):
    if not label.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("label must contain only letters, digits, _ or -")
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    stem = f"{now:%Y%m%dT%H%M%SZ}-{label}"
    commands = {
        "gauge": ["idevicediagnostics", "diagnostics", "GasGauge"],
        "battery": ["ideviceinfo", "-q", "com.apple.mobile.battery", "-x"],
        "charger": ["idevicediagnostics", "ioregentry", "AppleARMPMUCharger"],
    }
    report = {"captured_utc": now.isoformat(), "label": label}
    for name, command in commands.items():
        raw = run(command)
        parsed = plistlib.loads(raw)
        (OUT / f"{stem}-{name}.plist").write_bytes(raw)
        report[name] = dict(flatten(parsed))
    path = OUT / f"{stem}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(path)
    for section in ("gauge", "battery", "charger"):
        for key, value in report[section].items():
            if any(token in key.lower() for token in
                   ("capacity", "current", "amperage", "charge", "voltage", "soc", "cycle", "temperature")):
                print(f"{section}.{key}={value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", help="baseline or after-linux")
    capture(parser.parse_args().label)

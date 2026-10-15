#!/usr/bin/env python3
"""Start or collect the RAM-only A6 power journal over the USB shell."""

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "rootfs/a6-power-longrun.sh"
REMOTE = "/tmp/a6-power-longrun.sh"
ENCODED = "/tmp/a6-power-longrun.b64"
LOG = "/tmp/a6-power-longrun.log"
PIDFILE = "/tmp/a6-power-longrun.pid"


def serial(command: str, marker: str, timeout: int = 15) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/a6-usb-acm-direct.py"),
         command, "--until", marker, "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 10, check=False,
    )
    if result.returncode or not re.search(
        rf"(?:^|\r?\n){re.escape(marker)}(?:\r?\n|$)", result.stdout
    ):
        raise RuntimeError(f"phone command failed: {result.stderr[-400:]} "
                           f"{result.stdout[-400:]}")
    return result.stdout


def start() -> None:
    blob = SOURCE.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    encoded = base64.b64encode(blob).decode("ascii")
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", encoded):
        raise RuntimeError("unexpected base64 characters")
    serial(f": > {ENCODED}; echo A6_POWER_CLEAR", "A6_POWER_CLEAR")
    for offset in range(0, len(encoded), 96):
        chunk = encoded[offset:offset + 96]
        serial(f"printf '%s' '{chunk}' >> {ENCODED}; echo A6_POWER_CHUNK",
               "A6_POWER_CHUNK")
    output = serial(
        f"/bin/busybox base64 -d {ENCODED} > {REMOTE} && "
        f"/bin/busybox sha256sum {REMOTE}; echo A6_POWER_HASH",
        "A6_POWER_HASH",
    )
    if not re.search(rf"\b{digest}\s+{re.escape(REMOTE)}\b", output):
        raise RuntimeError("phone-side journal hash mismatch")
    serial(
        "test -r /sys/firmware/a6_charger_policy/status && "
        "test -r /sys/firmware/a6_charger_policy/samples && "
        "test -r /sys/firmware/a6_charger_policy/low_battery_status && "
        "/bin/busybox gzip --help >/dev/null 2>&1 && "
        "echo A6_POWER_PREFLIGHT",
        "A6_POWER_PREFLIGHT",
    )
    serial(
        f"/bin/busybox setsid /bin/busybox sh {REMOTE} "
        "</dev/null >/tmp/a6-power-longrun-start.log 2>&1 & "
        "echo A6_POWER_STARTED",
        "A6_POWER_STARTED",
    )
    status = serial(
        f"sleep 1; pid=$(cat {PIDFILE}) && kill -0 \"$pid\" && "
        f"head -n 1 {LOG}; echo A6_POWER_ALIVE",
        "A6_POWER_ALIVE",
    )
    if "A6_POWER_LONGRUN_V1" not in status:
        raise RuntimeError("journal did not start")
    print(f"Phone RAM power journal running; script SHA-256 {digest}")


def preflight() -> None:
    def snapshot() -> tuple[str, int]:
        output = serial(
            f"pid=$(cat {PIDFILE}) && kill -0 \"$pid\" && "
            "cat /sys/firmware/a6_charger_policy/status && "
            "cat /sys/firmware/a6_charger_policy/low_battery_status && "
            f"/bin/busybox wc -c {LOG}; echo A6_POWER_PREFLIGHT_END",
            "A6_POWER_PREFLIGHT_END",
        )
        charger = re.search(r"A6_D1972_500_CLASS_CANDIDATE_V5[^\r\n]*", output)
        auto = re.search(r"(?m)^auto=[^\r\n]*", output)
        if not charger or not auto:
            raise RuntimeError("charger policy status is missing")
        for line, field in ((auto.group(), "auto=1"),
                            (auto.group(), "paused=0"),
                            (auto.group(), "fault=0"),
                            (auto.group(), "attached=1")):
            if not re.search(rf"(?:^| ){re.escape(field)}(?: |$)", line):
                raise RuntimeError(f"charger policy has wrong {field}")
        low = re.search(r"A6_LOW_BATTERY_CANDIDATE_V3[^\r\n]*", output)
        if not low:
            raise RuntimeError("normal low-battery monitor status is missing")
        for field in ("enabled=1", "attended_trial=0", "attended_plugged=0",
                      "threshold_mv=3600", "plugged_critical_mv=3400"):
            if not re.search(rf"(?:^| ){re.escape(field)}(?: |$)", low.group()):
                raise RuntimeError(f"low-battery monitor has wrong {field}")
        size = re.search(rf"(?m)^\s*(\d+)\s+{re.escape(LOG)}\r?$", output)
        if not size:
            raise RuntimeError("RAM journal is missing or its worker stopped")
        return output, int(size.group(1))

    _, first = snapshot()
    time.sleep(32)
    output, second = snapshot()
    if second <= first:
        raise RuntimeError(f"RAM journal did not grow: {first} -> {second} bytes")
    print(f"PASS automatic policy enabled, no fault, normal 3600 mV monitor, journal alive "
          f"and growing ({first} -> {second} bytes)")
    print(next(line for line in output.splitlines()
               if "A6_LOW_BATTERY_CANDIDATE_V3 enabled=1" in line))


def collect() -> None:
    # Freeze the compressed file, then authenticate its complete USB transfer.
    nonce = uuid.uuid4().hex[:12]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "logs/power"
    folder.mkdir(parents=True, exist_ok=True)
    capture = folder / f"{stamp}-{nonce}-a6-power-longrun.console.txt"
    packed = "/tmp/a6-power-snapshot.gz"
    begin, end, done = (f"A6_POWER_{part}_{nonce}" for part in ("BEGIN", "END", "DONE"))
    command = (f"/bin/busybox gzip -c {LOG} > {packed} && "
               f"/bin/busybox sha256sum {packed} && "
               f"printf '\\n{begin}\\n' && /bin/busybox base64 {packed}; "
               f"printf '\\n{end}\\n'; echo A6_POWER_\"DONE\"_{nonce}")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/a6-usb-acm-direct.py"), command,
         "--until", done, "--timeout", "120"], capture_output=True, text=True,
    )
    capture.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"journal transfer failed; partial evidence at {capture}")
    output = result.stdout.replace("\r", "")
    match = re.search(rf"(?:^|\n){begin}\n([A-Za-z0-9+/=\n]+?)\n{end}(?:\n|$)", output)
    phone_hash = re.search(rf"\b([0-9a-f]{{64}})\s+{re.escape(packed)}\b", output)
    if not match or not phone_hash:
        raise RuntimeError(f"could not isolate authenticated journal payload; evidence at {capture}")
    payload = base64.b64decode("".join(match.group(1).split()), validate=True)
    if hashlib.sha256(payload).hexdigest() != phone_hash.group(1):
        raise RuntimeError(f"journal transfer hash mismatch; evidence at {capture}")
    log = gzip.decompress(payload)
    if not log.startswith(b"A6_POWER_LONGRUN_V1 start_uptime="):
        raise RuntimeError("phone journal header mismatch")
    path = folder / f"{stamp}-a6-power-longrun.log"
    path.write_bytes(log)
    print(f"Saved {len(log)} bytes, {log.count(b'A6_POWER_SAMPLE=')} samples: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "preflight", "collect"))
    args = parser.parse_args()
    {"start": start, "preflight": preflight, "collect": collect}[args.action]()

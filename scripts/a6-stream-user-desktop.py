#!/usr/bin/env python3
"""Stream the pinned Arch user desktop into phone RAM without storing the gzip."""

import argparse
import hashlib
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "build/arch-bootstrap/arch-hyprland-user-desktop.tar.gz"
CHECKSUM = BUNDLE.parent / "arch-hyprland-user-desktop.sha256"
HOST = "192.168.7.2"
PORT = 8082
ROOT_ON_PHONE = "/tmp/graphics-runtime"


def serial(command: str, marker: str, timeout: int = 20) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/a6-usb-acm-direct.py"),
         command, "--until", marker, "--timeout", str(timeout)],
        text=True, capture_output=True, timeout=timeout + 10, check=False,
    )
    if result.returncode or not re.search(
        rf"(?:^|\r?\n){re.escape(marker)}(?:\r?\n|$)", result.stdout
    ):
        raise RuntimeError("phone shell failed: " + result.stderr[-400:] +
                           result.stdout[-400:])
    return result.stdout


def verify_bundle() -> tuple[str, int]:
    expected = CHECKSUM.read_text().split()[0]
    digest = hashlib.sha256()
    with BUNDLE.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise RuntimeError("desktop bundle SHA-256 mismatch")
    members = set()
    with tarfile.open(BUNDLE, "r:gz") as archive:
        for member in archive:
            if member.name in {
                "graphics-runtime/usr/bin/Hyprland",
                "graphics-runtime/usr/local/bin/a6-start-desktop",
                "graphics-runtime/usr/local/bin/a6-prepare-user-desktop",
                "graphics-runtime/usr/local/bin/a6-start-user-hyprland",
            }:
                members.add(member.name)
    if len(members) != 4:
        raise RuntimeError("desktop bundle is missing a required launcher")
    return expected, BUNDLE.stat().st_size


def phone_preflight() -> None:
    output = serial(
        "test ! -e /tmp/graphics-runtime && "
        "test -c /dev/dri/card0 && "
        "test -r /sys/firmware/a6_charger_policy/status && "
        "test -r /sys/firmware/a6_charger_policy/low_battery_status && "
        "grep -q '^auto=1 paused=0 fault=0 ' "
        "/sys/firmware/a6_charger_policy/status && "
        "grep -q '^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 ' "
        "/sys/firmware/a6_charger_policy/low_battery_status && "
        "awk '/^MemAvailable:/ { if ($2 < 500000) exit 1; found=1 } END { if (!found) exit 1 }' "
        "/proc/meminfo && echo A6_DESKTOP_PREFLIGHT",
        "A6_DESKTOP_PREFLIGHT",
    )
    if "A6_DESKTOP_PREFLIGHT" not in output:
        raise RuntimeError("desktop preflight did not complete")


def deploy(size: int) -> None:
    phone_preflight()
    try:
        with socket.create_connection((HOST, 8080), timeout=5):
            pass
    except OSError as exc:
        raise RuntimeError("USB Ethernet is not ready; run the host 'up' helper") from exc

    token = secrets.token_hex(4)
    status = f"/tmp/a6-desktop-stream-{token}.status"
    pid = f"/tmp/a6-desktop-stream-{token}.pid"
    log = f"/tmp/a6-desktop-stream-{token}.log"

    worker = (
        f"echo $$ > {pid}; "
        f"/bin/busybox nc -l -p {PORT} | "
        f"/bin/busybox tar -xz -C /tmp > {log} 2>&1; "
        f"echo $? > {status}"
    )
    # The worker writes its own PID; $! can name a short-lived setsid parent.
    serial(
        f"test ! -e {status} && test ! -e {pid} && "
        f"/bin/busybox setsid /bin/busybox sh -c '{worker}' "
        "</dev/null >/dev/null 2>&1 & echo A6_DESKTOP_WORKER_STARTED",
        "A6_DESKTOP_WORKER_STARTED",
    )
    serial(f"test -s {pid} && kill -0 \"$(cat {pid})\" && "
           "echo A6_DESKTOP_WORKER_ALIVE", "A6_DESKTOP_WORKER_ALIVE")

    sent = 0
    with socket.create_connection((HOST, PORT), timeout=10) as target:
        target.settimeout(60)
        with BUNDLE.open("rb") as source:
            # PIO ECM can stall under an unbounded bulk burst. Keep the
            # stream below 1 MiB/s; verify the extracted file manifest afterwards.
            for block in iter(lambda: source.read(65536), b""):
                target.sendall(block)
                sent += len(block)
                time.sleep(0.0625)
        target.shutdown(socket.SHUT_WR)
    if sent != size:
        raise RuntimeError(f"short host stream: {sent} of {size} bytes")

    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        output = serial(f"if test -f {status}; then printf 'A6_RESULT='; "
                        f"cat {status}; fi; echo A6_DESKTOP_STATUS",
                        "A6_DESKTOP_STATUS")
        match = re.search(r"A6_RESULT=(\d+)", output)
        if match:
            if match.group(1) != "0":
                raise RuntimeError("phone extractor failed; inspect " + log)
            break
        time.sleep(2)
    else:
        raise RuntimeError("phone extractor did not finish")

    serial(
        f"test -x {ROOT_ON_PHONE}/usr/bin/Hyprland && "
        f"test -x {ROOT_ON_PHONE}/usr/local/bin/a6-start-user-hyprland && "
        "echo A6_DESKTOP_EXTRACTED", "A6_DESKTOP_EXTRACTED",
    )
    print(f"PASS {size} verified compressed bytes streamed into phone RAM")
    print("Arch tree:", ROOT_ON_PHONE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "deploy"))
    args = parser.parse_args()
    digest, size = verify_bundle()
    print(f"Verified desktop bundle: {size} bytes, SHA-256 {digest}")
    if args.action == "deploy":
        deploy(size)

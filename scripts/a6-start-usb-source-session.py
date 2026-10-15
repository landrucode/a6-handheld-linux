#!/usr/bin/env python3
"""Stage and start an attended PMU/UDC reconnect trial in phone RAM."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--seconds", type=int,
                    help="preventive watcher duration, 1–3600 seconds (not used with --delayed-recovery)")
parser.add_argument("--delayed-recovery", action="store_true",
                    help="let native reconnect run, then perform one delayed UDC cycle")
parser.add_argument("--recovery-delay", type=int, default=120,
                    help="delay before one UDC cycle, 5–180 seconds (default: 120)")
parser.add_argument("--collect", action="store_true",
                    help="save phone/host evidence on native return or delayed UDC recovery")
parser.add_argument("--short-interval", action="store_true",
                    help="sample PMU every 100 ms for an attended sub-second cable break")
args = parser.parse_args()
if args.collect and not args.delayed_recovery:
    parser.error("--collect requires --delayed-recovery")
if args.short_interval and not args.delayed_recovery:
    parser.error("--short-interval requires --delayed-recovery")
if args.delayed_recovery and args.seconds is not None:
    parser.error("--seconds cannot be used with --delayed-recovery")
if not args.delayed_recovery and args.recovery_delay != 120:
    parser.error("--recovery-delay requires --delayed-recovery")
if not 5 <= args.recovery_delay <= 180:
    parser.error("--recovery-delay must be 5–180 seconds")
seconds = 600 if args.seconds is None else args.seconds
if not 1 <= seconds <= 3600:
    parser.error("--seconds must be 1–3600")
name = "a6-usb-delayed-recovery" if args.delayed_recovery else "a6-usb-source-session"
source = repo / f"rootfs/{name}.sh"
remote = f"/tmp/{name}.sh"
encoded_remote = f"/tmp/{name}.b64"
log = f"/tmp/{name}.log"
pidfile = f"/tmp/{name}.pid"


def serial(command: str, marker: str, timeout: int = 15) -> str:
    result = subprocess.run(
        [sys.executable, str(repo / "scripts/a6-usb-acm-direct.py"),
         command, "--until", marker, "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 10,
        check=False,
    )
    if result.returncode or marker not in result.stdout:
        raise RuntimeError(f"phone command failed: {result.stderr[-400:]} "
                           f"{result.stdout[-400:]}")
    return result.stdout


blob = source.read_bytes()
digest = hashlib.sha256(blob).hexdigest()
encoded = base64.b64encode(blob).decode("ascii")
assert re.fullmatch(r"[A-Za-z0-9+/=]+", encoded)
serial(f": > {encoded_remote}; echo A6_SOURCE_CLEAR_OK", "A6_SOURCE_CLEAR_OK")
for offset in range(0, len(encoded), 96):
    chunk = encoded[offset:offset + 96]
    serial(f"printf '%s' '{chunk}' >> {encoded_remote}; "
           "echo A6_SOURCE_CHUNK_OK", "A6_SOURCE_CHUNK_OK")
output = serial(
    f"/bin/busybox base64 -d {encoded_remote} > {remote} "
    f"&& /bin/busybox sha256sum {remote} "
    "&& echo A6_SOURCE_UPLOAD_OK",
    "A6_SOURCE_UPLOAD_OK",
)
if not re.search(rf"\b{digest}\s+{re.escape(remote)}\b", output):
    raise RuntimeError("phone-side script hash did not match")

preflight = serial(
    "test -w /sys/class/udc/36100000.usb/soft_connect "
    "&& test -r /sys/class/power_supply/a6-d1972-usb/online "
    "&& test \"$(cat /sys/class/power_supply/a6-d1972-usb/online)\" = 1 "
    "&& /bin/busybox setsid --help >/dev/null 2>&1 "
    "&& echo A6_SOURCE_PREFLIGHT_OK",
    "A6_SOURCE_PREFLIGHT_OK",
)
serial(
    (f"A6_USB_RECOVERY_DELAY={args.recovery_delay} "
     + ("A6_USB_RECOVERY_LIMIT=6000 A6_USB_RECOVERY_INTERVAL_US=100000 "
        if args.short_interval else "A6_USB_RECOVERY_LIMIT=600 ")
     if args.delayed_recovery else f"A6_USB_SESSION_SAMPLES={seconds} ") +
    "/bin/busybox setsid "
    f"/bin/busybox sh {remote} </dev/null >{log} 2>&1 & "
    "echo A6_SOURCE_START_OK",
    "A6_SOURCE_START_OK",
)
status = serial(f"sleep 1; cat {log}; echo A6_SOURCE_STATUS_OK",
                "A6_SOURCE_STATUS_OK")
armed = "a6-delayed-recovery: armed" if args.delayed_recovery else "a6-usb-source-session: armed"
if armed not in status:
    raise RuntimeError(f"session did not arm: {status[-500:]}")
if args.delayed_recovery:
    serial(f"pid=$(cat {pidfile}) && kill -0 \"$pid\" "
           "&& echo A6_SOURCE_PID_OK", "A6_SOURCE_PID_OK")
print(f"Phone RAM {name} armed; script SHA256 {digest}")

if args.collect:
    def gadget_device() -> str | None:
        for entry in Path("/sys/bus/usb/devices").iterdir():
            try:
                if (entry / "idVendor").read_text().strip() == "0525" and \
                   (entry / "idProduct").read_text().strip() == "a4aa":
                    return f"{entry.name}:{(entry / 'devnum').read_text().strip()}"
            except (OSError, ValueError):
                continue
        return None

    initial_device = gadget_device()
    if initial_device is None:
        raise RuntimeError("gadget disappeared before collection was armed")
    started = datetime.now(timezone.utc)
    deadline = time.monotonic() + 900
    print(f"Watching for a new A6 gadget after {initial_device}; up to 15 minutes", flush=True)
    phone_capture = None
    new_device = None
    recovery_kind = "unavailable"
    interrupted = False
    try:
        while time.monotonic() < deadline:
            time.sleep(2)
            current = gadget_device()
            if current is None or current == initial_device:
                continue
            try:
                state = serial(
                    "cat /tmp/a6-usb-delayed-recovery.log; echo A6_RECOVERY_STATE_DONE",
                    "A6_RECOVERY_STATE_DONE", timeout=10,
                )
            except (RuntimeError, subprocess.TimeoutExpired):
                continue
            if "one-shot complete" in state:
                recovery_kind = "delayed_udc"
            elif f"PMU returned; native USB has {args.recovery_delay}s" in state:
                try:
                    serial(f"pid=$(cat {pidfile}) && kill -0 \"$pid\" "
                           "&& kill \"$pid\" && echo A6_NATIVE_STOP_OK",
                           "A6_NATIVE_STOP_OK")
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    raise RuntimeError(f"native USB returned but watcher stop failed: {error}")
                recovery_kind = "native_before_fallback"
            else:
                continue
            new_device = current
            try:
                phone_capture = serial(
                    "echo A6_LATCH_BEGIN; "
                    "if test -r /sys/class/udc/36100000.usb/device/a6_lx_latch; "
                    "then cat /sys/class/udc/36100000.usb/device/a6_lx_latch; fi; "
                    "echo A6_STAGE_BEGIN; "
                    "cat /sys/class/udc/36100000.usb/device/a6_usb_stage; "
                    "echo A6_RECOVERY_LOG_BEGIN; cat /tmp/a6-usb-delayed-recovery.log; "
                    "echo A6_DMESG_BEGIN; dmesg | tail -n 200; "
                    "echo A6_CAPTURE_DONE",
                    "A6_CAPTURE_DONE", timeout=60,
                )
            except (RuntimeError, subprocess.TimeoutExpired):
                phone_capture = state
            break
    except KeyboardInterrupt:
        interrupted = True
    finally:
        host_capture = subprocess.run(
            ["journalctl", "-k", "--since", started.strftime("%Y-%m-%d %H:%M:%S UTC"),
             "--no-pager"], capture_output=True, text=True, check=False,
        )
        host_log = host_capture.stdout
        before_recovery = host_log.split("New USB device found, idVendor=0525", 1)[0]
        counts = {code: len(re.findall(rf"error {code}\b", before_recovery))
                  for code in ("-110", "-71", "-62")}
        first_failure = re.search(r"^.*a6-usb-lx-first:.*$", phone_capture or "",
                                  re.MULTILINE)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        output_dir = repo / "logs/usb"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{stamp}-lx-recovery.txt"
        payload = (f"started_utc={started.isoformat()}\n"
                   f"initial_device={initial_device}\nnew_device={new_device}\n"
                   f"phone_capture={'complete' if phone_capture else 'unavailable'}\n"
                   f"recovery_kind={recovery_kind}\n"
                   f"interrupted={int(interrupted)}\n"
                   f"journalctl_exit={host_capture.returncode}\n"
                   f"pre_recovery_errors=-110:{counts['-110']} "
                   f"-71:{counts['-71']} -62:{counts['-62']}\n"
                   f"first_failure_printk={first_failure.group(0) if first_failure else 'unavailable'}\n"
                   f"\nHOST KERNEL LOG\n{host_log}\n"
                   f"\nHOST KERNEL ERRORS\n{host_capture.stderr}\n"
                   f"\nPHONE CAPTURE\n{phone_capture or ''}\n")
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(payload)
        print(f"Saved recovery evidence to {output_path}")
    if interrupted:
        print("Collection interrupted after saving partial evidence", file=sys.stderr)
        raise SystemExit(130)
    if phone_capture is None:
        raise RuntimeError("phone shell did not return with a completed one-shot log")

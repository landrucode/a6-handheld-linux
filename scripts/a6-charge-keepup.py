#!/usr/bin/env python3
"""Keep-up test: does Linux charging raise the battery under the current load?

Enables automatic charging, then alternates charge and pause phases while the
kernel samples VBAT every two seconds. Pausing stops the charge request but
keeps the 480 mA input supply, so the load stays the same. A VBAT step up at
each resume and down at each pause is a Linux-local signature of charge
current; the VBAT slope while charging shows whether the cell gains charge.
Evidence is saved under logs/charging/ (gitignored, mode 0600).
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[1]
policy = "/sys/firmware/a6_charger_policy"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--phase-seconds", type=int, default=120,
                    help="length of each charge/pause phase, 60-200 seconds")
parser.add_argument("--final", choices=("auto", "pause", "disarm"), default="auto",
                    help="policy state to leave the phone in afterwards")
parser.add_argument("--max-start-mv", type=int, default=4000,
                    help="refuse to start above this VBAT (needs headroom below 4250)")
args = parser.parse_args()
if not 60 <= args.phase_seconds <= 200:
    parser.error("--phase-seconds must be 60-200 (the kernel keeps 256 s of samples)")


def serial(command: str, marker: str, timeout: int = 20) -> str:
    result = subprocess.run(
        [sys.executable, str(repo / "scripts/a6-usb-acm-direct.py"),
         command, "--until", marker, "--timeout", str(timeout)],
        capture_output=True, text=True, timeout=timeout + 10, check=False,
    )
    if result.returncode or marker not in result.stdout:
        raise RuntimeError(f"phone command failed: {result.stderr[-400:]} "
                           f"{result.stdout[-400:]}")
    return result.stdout


def status() -> str:
    return serial(f"cat {policy}/status; echo A6_KEEPUP_STATUS_OK",
                  "A6_KEEPUP_STATUS_OK")


def field(text: str, name: str) -> int:
    match = re.search(rf"\b{name}=(-?\d+)", text)
    if not match:
        raise RuntimeError(f"{name} missing from policy status:\n{text[-600:]}")
    return int(match.group(1))


def control(command: str) -> None:
    serial(f"echo {command} > {policy}/control && echo A6_KEEPUP_CONTROL_OK",
           "A6_KEEPUP_CONTROL_OK")


def preflight_vbat() -> int:
    previous = serial("cat /sys/firmware/a6_vbat_adc/status; echo A6_VBAT_READY",
                      "A6_VBAT_READY")
    remaining_ticks = field(previous, "next_jiffies") - field(previous, "now_jiffies")
    if remaining_ticks > 0:
        # The restored one-shot probe has a 60-second cooldown (HZ=100).
        time.sleep(remaining_ticks / 100 + 1)
    reading = serial(
        "echo sample-vbat-and-restore > /sys/firmware/a6_vbat_adc/sample; "
        "echo A6_VBAT_SAMPLE_RC=$?; cat /sys/firmware/a6_vbat_adc/status; "
        "echo A6_KEEPUP_VBAT_OK", "A6_KEEPUP_VBAT_OK")
    if "A6_VBAT_SAMPLE_RC=0" not in reading or field(reading, "result") or \
            field(reading, "cleanup_result") or field(reading, "restored") != 1:
        raise RuntimeError(f"restored VBAT preflight failed:\n{reading}")
    log_lines.extend(["VBAT PREFLIGHT", reading.strip()])
    return field(reading, "vbat_candidate_mv")


samples: dict[int, tuple[str, int, int, int]] = {}
hz = 100


def pull_samples() -> None:
    global hz
    text = serial(f"cat {policy}/samples; echo A6_KEEPUP_SAMPLES_OK",
                  "A6_KEEPUP_SAMPLES_OK")
    header = re.search(r"A6_D1972_AUTO_SAMPLES_V1 hz=(\d+)", text)
    if not header:
        raise RuntimeError("sample log missing; is this the V4 policy image?")
    hz = int(header.group(1))
    for when, state, vbus, vbat, tbat in re.findall(
            r"^(\d+) ([A-Z]) (\d+) (\d+) (-?\d+)\s*$", text, re.MULTILINE):
        samples[int(when)] = (state, int(vbus), int(vbat), int(tbat))


def wait_for(active: bool, seconds: int = 40) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        text = status()
        if field(text, "fault"):
            raise RuntimeError(f"policy fault:\n{text}")
        if bool(field(text, "active")) == active:
            return text
        time.sleep(2)
    raise RuntimeError(f"charging did not become active={int(active)} in {seconds}s:\n{text}")


started = datetime.now(timezone.utc)
log_lines = [f"started_utc={started.isoformat()}",
             f"phase_seconds={args.phase_seconds}"]
initial = status()
log_lines += ["INITIAL STATUS", initial.strip()]
if not any(f"A6_D1972_500_CLASS_CANDIDATE_V{version}" in initial
           for version in (4, 5)):
    sys.exit("phone is not running a V4/V5 automatic charger policy image")
vbat = preflight_vbat()
if vbat > args.max_start_mv:
    sys.exit(f"VBAT {vbat} mV is above {args.max_start_mv} mV; run nearer 50% charge")

phases = []
failure = None
try:
    control("auto")
    armed = wait_for(True, seconds=150)
    if field(armed, "vbat_mv") > args.max_start_mv:
        raise RuntimeError(f"VBAT {field(armed, 'vbat_mv')} mV is above "
                           f"{args.max_start_mv} mV; run nearer 50% charge")
    for name in ("charge", "pause", "charge", "pause"):
        if name == "pause":
            control("pause")
            wait_for(False)
        elif phases:
            control("auto")
            # A pause imposes the kernel's 120-second rearm gap.
            wait_for(True, seconds=150)
        phases.append((name, time.monotonic()))
        print(f"{name} phase: {args.phase_seconds}s", flush=True)
        time.sleep(args.phase_seconds)
        pull_samples()
except Exception as error:
    failure = error
    log_lines.append(f"TRIAL INCOMPLETE: {type(error).__name__}: {error}")
finally:
    try:
        control(args.final)
        final = status()
        log_lines += [f"FINAL STATE REQUESTED={args.final}", "FINAL STATUS", final.strip()]
    except RuntimeError as error:
        log_lines.append(f"final control failed: {error}")
    try:
        pull_samples()
    except RuntimeError as error:
        log_lines.append(f"final sample collection failed: {error}")

ordered = sorted(samples.items())
# Kernel jiffies is 32-bit on this phone and may wrap during a trial. The
# collection spans minutes, so a spread over half the counter range uniquely
# identifies the wrap; put the high values before the low values.
if ordered and ordered[-1][0] - ordered[0][0] > (1 << 31):
    wrap = next(i for i, (when, _) in enumerate(ordered) if when >= (1 << 31))
    ordered = ordered[wrap:] + ordered[:wrap]
steps = []
for index in range(1, len(ordered)):
    before_state = ordered[index - 1][1][0]
    after_state = ordered[index][1][0]
    if {before_state, after_state} != {"C", "P"}:
        continue
    before = [s[2] for _, s in ordered[max(0, index - 5):index] if s[0] == before_state]
    after = [s[2] for _, s in ordered[index:index + 5] if s[0] == after_state]
    if before and after:
        steps.append((f"{before_state}->{after_state}",
                      statistics.mean(after) - statistics.mean(before)))

slopes = []
run: list[tuple[int, int]] = []
run_state = None
for when, (state, _vbus, vbat_mv, _tbat) in ordered + [(0, ("END", 0, 0, 0))]:
    if state != run_state:
        if run_state in ("C", "P") and len(run) >= 10:
            t0 = run[0][0]
            xs = [((w - t0) % (1 << 32)) / hz / 60 for w, _ in run]
            ys = [v for _, v in run]
            mx, my = statistics.mean(xs), statistics.mean(ys)
            denom = sum((x - mx) ** 2 for x in xs)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0
            slopes.append((run_state, slope, len(run)))
        run, run_state = [], state
    run.append((when, vbat_mv))

log_lines.append("STEPS (mean of 5 samples after minus 5 before, mV)")
log_lines += [f"{kind} {delta:+.1f}" for kind, delta in steps]
log_lines.append("SLOPES (VBAT mV/min per phase)")
log_lines += [f"{state} {slope:+.2f} over {n} samples" for state, slope, n in slopes]
up = [d for k, d in steps if k == "P->C"]
down = [d for k, d in steps if k == "C->P"]
signature = bool(up) and bool(down) and min(up) > 15 and max(down) < -15
charge_slopes = [s for st, s, _ in slopes if st == "C"]
verdict = (["incomplete: no charging verdict"] if failure is not None else [
    f"charge_current_signature={'yes' if signature else 'no'}",
    ("vbat_rising_while_charging=" +
     ("yes" if charge_slopes and statistics.mean(charge_slopes) > 0 else "no")),
])
log_lines += ["VERDICT"] + verdict
log_lines.append("SAMPLES (jiffies state vbus vbat tbat)")
log_lines += [f"{w} {s[0]} {s[1]} {s[2]} {s[3]}" for w, s in ordered]

output_dir = repo / "logs/charging"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}-keepup.txt"
fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    handle.write("\n".join(log_lines) + "\n")
print("\n".join(f"{k} {d:+.1f} mV" for k, d in steps))
print("\n".join(verdict))
print(f"Saved keep-up evidence to {output_path}")
if failure is not None:
    raise RuntimeError(f"keep-up trial incomplete; evidence saved to {output_path}") from failure

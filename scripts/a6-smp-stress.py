#!/usr/bin/env python3
"""Upload a verified bounded stress workload after the kernel integration PASS."""
import argparse
import base64
import hashlib
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("power_transport", ROOT / "scripts/a6-phone-power-log.py")
power = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("mode", choices=("start", "collect"))
args = parser.parse_args()
if args.mode == "collect":
    output = power.serial("cat /tmp/a6-smp-stress.log; echo A6_STRESS_END", "A6_STRESS_END")
    folder = ROOT / "logs/smp"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (power.datetime.now(power.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-smp-stress.console.txt")
    path.write_text(output)
    if "A6_SMP_STRESS_V1 result=0" not in output or len(re.findall(r"PASS cpu=[01] loops=[1-9]\d*", output)) != 2:
        raise SystemExit(f"stress not complete or failed; retained {path}")
    print(f"PASS two-core 120-second hash/fork workload: {path}")
else:
    status = power.serial("cat /sys/firmware/a6_smp_bridge/probe_status; echo A6_PROBE_END", "A6_PROBE_END")
    if not re.search(r"phase=3 result=0 .*controls=32 ranges=16 full=16", status):
        raise SystemExit("kernel integration proof has not passed")
    source = (ROOT / "rootfs/a6-smp-stress.sh").read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    encoded = base64.b64encode(source).decode()
    power.serial(": > /tmp/a6-stress.b64; echo A6_STRESS_CLEAR", "A6_STRESS_CLEAR")
    for offset in range(0, len(encoded), 96):
        power.serial(f"printf '%s' '{encoded[offset:offset+96]}' >> /tmp/a6-stress.b64; echo A6_STRESS_CHUNK", "A6_STRESS_CHUNK")
    power.serial("base64 -d /tmp/a6-stress.b64 > /tmp/a6-smp-stress.sh; echo A6_STRESS_DECODE", "A6_STRESS_DECODE")
    raw = power.serial("sha256sum /tmp/a6-smp-stress.sh; echo A6_STRESS_HASH", "A6_STRESS_HASH")
    if digest not in raw:
        raise SystemExit("phone workload hash mismatch")
    power.serial("busybox setsid busybox sh /tmp/a6-smp-stress.sh </dev/null >/tmp/a6-stress-start.log 2>&1 & echo A6_STRESS_START", "A6_STRESS_START")
    power.serial('sleep 1; pid=$(cat /tmp/a6-smp-stress.pid); kill -0 "$pid" && echo A6_STRESS_ALIVE', "A6_STRESS_ALIVE")
    print(f"Two-core bounded RAM workload running; SHA-256 {digest}")

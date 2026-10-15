#!/usr/bin/env python3
"""Compare iOS gauge capacity around a measured Linux USB interval."""
import argparse
import datetime as dt
import json
from pathlib import Path


def instant(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("baseline", type=Path)
parser.add_argument("after", type=Path)
parser.add_argument("--linux-start", required=True, help="UTC ISO timestamp of bootx")
parser.add_argument("--linux-end", required=True, help="UTC ISO timestamp Linux stopped")
parser.add_argument("--source-ma", type=float, default=500,
                    help="assumed maximum USB input current in mA (default: reported 500)")
parser.add_argument("--source-v-max", type=float, default=5.25,
                    help="conservative maximum USB input voltage (default: 5.25 V)")
parser.add_argument("--cell-v-min", type=float, default=3.6,
                    help="conservative minimum battery voltage (default: 3.6 V)")
parser.add_argument("--uncertainty-mah", type=float, default=10)
parser.add_argument("--max-raw-max-drift-pct", type=float, default=1,
                    help="largest raw-maximum change accepted for normalized comparison")
args = parser.parse_args()
if (min(args.source_ma, args.source_v_max, args.cell_v_min) <= 0 or
        args.uncertainty_mah < 0 or args.max_raw_max_drift_pct < 0):
    parser.error("currents and voltages must be positive; uncertainty must be nonnegative")
before = json.loads(args.baseline.read_text())
after = json.loads(args.after.read_text())
t0, t1 = instant(before["captured_utc"]), instant(after["captured_utc"])
start, end = instant(args.linux_start), instant(args.linux_end)
if not t0 <= start < end <= t1:
    parser.error("timestamps must order baseline <= Linux start < end <= after")
outside_h = ((start - t0) + (t1 - end)).total_seconds() / 3600
outside_battery_ma = args.source_ma * args.source_v_max / args.cell_v_min
outside_max = outside_h * outside_battery_ma
print(f"Linux interval: {(end-start).total_seconds()/3600:.2f} h")
print(f"Assumed USB input ceiling: {args.source_ma:g} mA at {args.source_v_max:g} V")
print(f"Ideal-conversion battery-current ceiling at {args.cell_v_min:g} V: "
      f"{outside_battery_ma:.1f} mA")
print(f"Conditional maximum charge during non-Linux gaps: {outside_max:.1f} mAh")
print(f"Additional gauge uncertainty allowance: {args.uncertainty_mah:g} mAh")
keys = ("IORegistry.AppleRawCurrentCapacity", "IORegistry.CurrentCapacity",
        "IORegistry.AbsoluteCapacity", "IORegistry.AppleRawMaxCapacity",
        "IORegistry.MaxCapacity", "IORegistry.CycleCount")
for key in keys:
    a = before["charger"].get(key)
    b = after["charger"].get(key)
    if a is None or b is None:
        print(f"{key}: unavailable")
    else:
        print(f"{key}: {a} -> {b} (delta {b-a:+})")
stable_keys = keys[3:]
required = keys[:2] + stable_keys
complete = all(key in before["charger"] and key in after["charger"] for key in required)
adapter_key = "IORegistry.AdapterDetails.Amperage"
voltage_key = "IORegistry.Voltage"
adapter = [snapshot["charger"].get(adapter_key) for snapshot in (before, after)]
voltage = [snapshot["charger"].get(voltage_key) for snapshot in (before, after)]
print(f"Reported iOS USB input classes before/after: {adapter}")
print(f"Reported iOS cell voltage before/after: {voltage} mV")
assumptions_observed = (all(isinstance(a, (int, float)) and 0 < a <= args.source_ma
                            for a in adapter) and
                        all(isinstance(v, (int, float)) and v >= args.cell_v_min * 1000
                            for v in voltage))
raw = (after["charger"].get(keys[0], 0) - before["charger"].get(keys[0], 0))
current = (after["charger"].get(keys[1], 0) - before["charger"].get(keys[1], 0))
raw_max_before = before["charger"].get(keys[3])
raw_max_after = after["charger"].get(keys[3])
max_capacity_stable = (complete and
                       before["charger"][keys[4]] == after["charger"][keys[4]] and
                       before["charger"][keys[5]] == after["charger"][keys[5]])
raw_max_drift_pct = (abs(raw_max_after - raw_max_before) / raw_max_before * 100
                     if complete and raw_max_before > 0 and raw_max_after > 0 else float("inf"))
raw_max_close = raw_max_drift_pct <= args.max_raw_max_drift_pct
normalized_raw_delta = (after["charger"][keys[0]] * raw_max_before /
                        raw_max_after - before["charger"][keys[0]]
                        if raw_max_close else float("nan"))
conservative_raw_delta = (raw - abs(raw_max_after - raw_max_before)
                          if raw_max_close else float("nan"))
print(f"Raw maximum drift: {raw_max_drift_pct:.2f}% "
      f"(allowed <= {args.max_raw_max_drift_pct:g}%)")
if raw_max_close:
    print(f"Raw gain normalized to baseline maximum: {normalized_raw_delta:.1f} mAh")
    print(f"Raw gain minus absolute maximum drift: {conservative_raw_delta:.1f} mAh")
if (complete and max_capacity_stable and raw_max_close and assumptions_observed and
        min(normalized_raw_delta, conservative_raw_delta) > outside_max + args.uncertainty_mah and
        current > outside_max + args.uncertainty_mah):
    print("RESULT: evidence of net battery capacity gain during Linux, conditional on the input-current ceiling and stable gauge scaling")
else:
    print("RESULT: Linux net charge remains unproven by this comparison")

#!/usr/bin/env python3
"""One-boot stock44 GPIO sweep, then an all-slot burst; never retry audio."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ladder', ROOT/'scripts/a6-run-audio-ladder.py')
ladder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ladder)


def unachieved_high(result, evidence):
    """Only a verified pre-play high-pin refusal allows the next variant."""
    status = result['status']
    if not re.search(r'tone_error=-5 samples=0 ', status):
        return False
    if not re.search(r'^attempted=1 result=-5 cleanup=0 ', status, re.M):
        return False
    if any((evidence/'amp-readbacks.private.bin').read_bytes()):
        return False
    pins = re.findall(r'ext_gpio(?:90|91)=([0-9a-f]+)/([0-9a-f]+)/([0-9a-f]+) observed=([0-9a-f]+)', status)
    if len(pins) != 2:
        return False
    mismatches = 0
    for before, expected, restored, observed in pins:
        a, b, c, d = (int(v, 16) for v in (before, expected, restored, observed))
        if a != c:
            return False
        if b != d:
            if not b & 1 or b ^ d != 1:
                return False
            mismatches += 1
    return bool(mismatches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    folder = ROOT/'build/session-logs'/('audio-switch-sweep-'+secrets.token_hex(8))
    folder.mkdir(mode=0o700)
    records = []
    # Low/low is the traced DT initialization, not a captured playback state.
    for state, all_slots in [(0, False), (1, False), (2, False), (3, False), (0, True)]:
        label = f'GPIO90={"high" if state&1 else "low"} GPIO91={"high" if state&2 else "low"}; '
        label += 'all eight slots' if all_slots else 'slot0'
        print(label+'; full scale, one second with ramps', flush=True)
        output = folder/f'state-{state}-allslots-{int(all_slots)}.private.log'
        with output.open('w') as stream:
            run = subprocess.run([sys.executable, str(ROOT/'scripts/a6-capture-audio-fifo.py'),
                                  '--stock44100', '--switch-state', str(state),
                                  *(['--all-slots'] if all_slots else []),
                                  '--broker', str(args.broker.resolve())],
                                 cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        match = re.search(r'Private evidence: (.+)', output.read_text())
        entry = {'gpio_state': state, 'all_slots': all_slots, 'returncode': run.returncode}
        if match:
            evidence = Path(match[1])
            result = json.loads((evidence/'result.private.json').read_text())
            entry.update(evidence=str(evidence), healthy_after=ladder.healthy(result.get('health_after', '')),
                         unachieved_high=run.returncode == 1 and unachieved_high(result, evidence))
        records.append(entry)
        (folder/'result.private.json').write_text(json.dumps(records, indent=2)+'\n')
        if not entry.get('healthy_after') or (run.returncode and not entry.get('unachieved_high')):
            print(f'Stopped: failed run or guard check; no replay. Evidence: {folder}', flush=True)
            return 1
        if entry.get('unachieved_high'):
            print('Requested high pin remained low; restored before playback. Advancing to a different variant.', flush=True)
    print(f'Sweep and all-slot attempt complete. Evidence: {folder}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

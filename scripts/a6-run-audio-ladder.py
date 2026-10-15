#!/usr/bin/env python3
"""Run the owner's bounded full-scale ladder once; never replay failed audio."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def healthy(text):
    required = ('auto=1', 'paused=0', 'fault=0', 'enabled=1', 'triggered=0', 'threshold_mv=3600')
    if not all(re.search(r'(?<!\w)' + value + r'(?!\w)', text) for value in required):
        return False
    voltages = [int(v) for v in re.findall(r'(?<!\w)vbat_mv=(\d+)', text)]
    temperature = re.search(r'tbat_c_candidate=(-?\d+)', text)
    return bool(voltages and min(voltages) >= 3600 and temperature and 10 <= int(temperature[1]) <= 35)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', type=Path, required=True)
    parser.add_argument('--variants', nargs='+', type=int, choices=(0, 4), default=[0, 4])
    parser.add_argument('--stock44100', action='store_true', help='observed stock44.1k amp-master configuration only')
    args = parser.parse_args()
    if args.stock44100:args.variants=[4]
    os.umask(0o077)
    folder = ROOT / 'build/session-logs' / ('audio-ladder-' + secrets.token_hex(8))
    folder.mkdir(mode=0o700)
    records = []
    for variant in dict.fromkeys(args.variants):
        for level, dbfs in enumerate((-20, -12, -6, -3, 0)):
            print(f'Variant {variant}: {dbfs} dBFS, one-second ramped burst', flush=True)
            output = folder / f'variant-{variant}-level-{level}.private.log'
            with output.open('w') as stream:
                run = subprocess.run([
                    sys.executable, str(ROOT / 'scripts/a6-capture-audio-fifo.py'),
                    *(['--stock44100'] if args.stock44100 else ['--reference', '--variant', str(variant)]),
                    '--level', str(level), '--broker', str(args.broker.resolve()),
                ], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            match = re.search(r'Private evidence: (.+)', output.read_text())
            entry = {'variant': variant, 'level': level, 'dbfs': dbfs, 'returncode': run.returncode}
            if match:
                evidence = Path(match[1])
                entry['evidence'] = str(evidence)
                result = json.loads((evidence / 'result.private.json').read_text())
                entry['healthy_after'] = healthy(result.get('health_after', ''))
            records.append(entry)
            (folder / 'result.private.json').write_text(json.dumps(records, indent=2) + '\n')
            if run.returncode or not entry.get('healthy_after'):
                print(f'Stopped after variant {variant}, level {dbfs}: failed run or guard check; no replay. Evidence: {folder}', flush=True)
                return 1
    print(f'Completed {"stock44.1k amplifier-master configuration" if args.stock44100 else "both requested clock roles"} through full scale. Evidence: {folder}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

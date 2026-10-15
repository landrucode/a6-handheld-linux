#!/usr/bin/env python3
"""Run the two captured-iOS-state bursts in one boot, without automatic retries."""
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


def verified(result, burst):
    status = result['status']
    required = [r'^attempted=1 result=0 cleanup=0 ',
                rf'^ios_playback_route=1 ios_amp_overrides={int(burst == 2)} rx_telemetry_disabled=1$',
                r'tone_route1=[0-9a-f]+/00000002/([0-9a-f]+)',
                r'monitor_counts=0/0/0',
                rf'nominal_frame_hz={48000 if burst == 2 else 44100} ']
    phases = re.findall(r'^amp_power_phase[012]=(.*)$', status, re.M)
    expected = {7: 0xf8 if burst == 2 else 0x30, 8: 0x49 if burst == 2 else 0x4b, 0x10: 0 if burst == 2 else 0x19}
    snapshots_ok = len(phases) == 3 and all(all(dict((int(k, 16), int(v, 16)) for k, v in re.findall(r'([0-9a-f]{2}):([0-9a-f]{2})', phase)).get(k) == v for k, v in expected.items()) for phase in phases)
    return snapshots_ok and all(re.search(pattern, status, re.M) for pattern in required) and ladder.healthy(result.get('health_after', ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    folder = ROOT/'build/session-logs'/('audio-ios-state-'+secrets.token_hex(8))
    folder.mkdir(mode=0o700)
    records = []
    for burst in (1, 2):
        print(f'Burst {burst}: {48000 if burst == 2 else 44100} Hz, route +24=2, RX disabled' + ('; amp 07=f8 08=49 10=00' if burst == 2 else '') + '; one second with ramps', flush=True)
        output = folder/f'burst-{burst}.private.log'
        with output.open('w') as stream:
            run = subprocess.run([sys.executable, str(ROOT/'scripts/a6-capture-audio-fifo.py'), '--ios-burst', str(burst), '--broker', str(args.broker.resolve())], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        match = re.search(r'Private evidence: (.+)', output.read_text())
        entry = {'burst': burst, 'returncode': run.returncode}
        if match:
            evidence = Path(match[1])
            result = json.loads((evidence/'result.private.json').read_text())
            entry.update(evidence=str(evidence), verified=verified(result, burst))
        records.append(entry)
        (folder/'result.private.json').write_text(json.dumps(records, indent=2)+'\n')
        if run.returncode or not entry.get('verified'):
            print(f'Stopped after failed run or verification; no replay. Evidence: {folder}', flush=True)
            return 1
    print(f'Both bursts complete. Evidence: {folder}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

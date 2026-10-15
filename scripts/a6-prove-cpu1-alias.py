#!/usr/bin/env python3
"""Invoke one RAM-side alias proof and retain/validate automatic evidence."""
import argparse
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

PATTERNS = {0: (0xa6c15a3c, 0x59e2a5c3), 4096: (0x3c5aa6c1, 0xc3a559e2)}


def validate(text):
    headers = re.findall(r'A6_CPU1_ALIAS_WRITE_V1 attempted=(\d+) result=(-?\d+) release_writes=(\d+)', text)
    if not headers or headers[-1] != ('1', '0', '0'):
        raise RuntimeError('proof did not complete successfully with CPU1 unreleased')
    rows = re.findall(r'offset=([0-9a-f]+) original=([0-9a-f]{8}) pattern0=([0-9a-f]{8}) ram0=([0-9a-f]{8}) zero0=([0-9a-f]{8}) pattern1=([0-9a-f]{8}) ram1=([0-9a-f]{8}) zero1=([0-9a-f]{8}) restore_ram=([0-9a-f]{8}) restore_zero=([0-9a-f]{8})', text)
    # Retain the final status rows; an earlier read may show attempted=0.
    final = {}
    for row in rows:
        values = tuple(int(value, 16) for value in row)
        final[values[0]] = values
    if set(final) != set(PATTERNS):
        raise RuntimeError('missing proof offsets')
    for offset, row in final.items():
        _, original, p0, ram0, zero0, p1, ram1, zero1, restored_ram, restored_zero = row
        if (p0, p1) != PATTERNS[offset] or (ram0, zero0) != (p0, p0) or (ram1, zero1) != (p1, p1):
            raise RuntimeError(f'pattern did not propagate at offset {offset:x}')
        if (restored_ram, restored_zero) != (original, original):
            raise RuntimeError(f'original was not restored at offset {offset:x}')
    return {'result': 'pass', 'offsets': sorted(final), 'already_attempted_at_first_status': headers[0][0] == '1', 'scope': 'CPU0 RAM-side writes; originals restored; no CPU1 release'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decode', type=Path, help='validate saved console without touching the phone')
    args = parser.parse_args()
    if args.decode:
        capture = args.decode
    else:
        nonce = uuid.uuid4().hex[:12]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        capture = Path('logs/smp') / f'{stamp}-cpu1-alias-write-{nonce}.console.txt'
        capture.parent.mkdir(parents=True, exist_ok=True)
        path = '/sys/firmware/a6_cpu1_alias/write_proof'
        marker = f'ALIAS_WRITE_{nonce}_DONE'
        command = f'cat {path}; echo prove > {path}; cat {path}; echo ALIAS_WRITE_{nonce}_"DONE"'
        helper = Path(__file__).with_name('a6-usb-acm-direct.py')
        with capture.open('wb') as stream:
            result = subprocess.run(['python3', str(helper), command, '--until', marker, '--timeout', '30'], stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'capture failed; partial evidence retained at {capture}')
    evidence = validate(capture.read_text(errors='replace'))
    manifest = capture.with_suffix('.json')
    manifest.write_text(json.dumps(evidence, indent=2) + '\n')
    print(f'PASS: both patterns propagated at both offsets; originals restored. Evidence: {capture}')


if __name__ == '__main__':
    main()

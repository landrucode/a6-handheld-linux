#!/usr/bin/env python3
"""Collect one bounded CPU0 remap -> CPU1 local-TLBI proof."""
import argparse
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from a6_cpu1_host_evidence import begin, finish


COMMANDS = (1, 1, 2, 3, 4)
VALUES = (0xa6a60011, 0xa6a60011, 0xb6b60022, 0xa6a60011, 0xb6b60022)


def validate(text):
    headers = re.findall(r'A6_CPU1_TLBI_V1 attempted=(\d+) result=(-?\d+) sent=(\d+) stage=(\d+) mmu_sctlr=([0-9a-f]{8})', text)
    if not headers or headers[0][0] != '0' or headers[-1][:3] != ('1', '0', '5'):
        raise RuntimeError('TLBI proof failed or incomplete; raw evidence retained')
    if int(headers[-1][4], 16) & 0x1005 != 1:
        raise RuntimeError('CPU1 MMU state not proven')
    rows = re.findall(r'phase=(\d+) tag=([0-9a-f]{8}) cmd=(\d+) count=(\d+) event=([0-9a-f]{8}) spsr=([0-9a-f]{8}) irq_cpsr=([0-9a-f]{8}) ack=([0-9a-f]{8}) value=([0-9a-f]{8}) fatal=(\d+)', text)
    final = {int(row[0]): row for row in rows}
    if set(final) != set(range(5)):
        raise RuntimeError('missing TLBI phase rows')
    for phase in range(5):
        row = final[phase]
        tag = 0xa6d10001 + phase
        observed = (int(row[1], 16), int(row[2]), int(row[3]), int(row[4], 16),
                    int(row[7], 16), int(row[8], 16), int(row[9]))
        wanted = (tag, COMMANDS[phase], phase + 3, 0x40001, tag, VALUES[phase], 0)
        if observed != wanted or int(row[5], 16) & 0x9f != 0x13 or int(row[6], 16) & 0x9f != 0x92:
            raise RuntimeError(f'TLBI phase {phase} mismatch')
    return {'result': 'pass', 'scope': 'private CPU1 MMU, stale negative control, local page/ASID/full TLBI via AIC IRQ; not Linux SMP scheduling or hardware broadcast'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decode', type=Path)
    args = parser.parse_args()
    if args.decode:
        capture = args.decode
    else:
        nonce = uuid.uuid4().hex[:12]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        capture = Path('logs/smp') / f'{stamp}-cpu1-tlbi-{nonce}.console.txt'
        capture.parent.mkdir(parents=True, exist_ok=True)
        path = '/sys/firmware/a6_cpu1_alias/tlbi_proof'
        helper = Path(__file__).with_name('a6-usb-acm-direct.py')
        since = begin(capture)
        try:
            with capture.open('wb') as stream:
                pre_marker = f'CPU1_TLBI_{nonce}_PRE'
                pre = subprocess.run(['python3', str(helper), f'cat {path}; echo CPU1_TLBI_{nonce}_"PRE"', '--until', pre_marker, '--timeout', '20'], stdout=stream, stderr=subprocess.STDOUT)
                stream.flush()
                if pre.returncode:
                    raise RuntimeError(f'pre-call capture failed; no proof submitted; evidence at {capture}')
                marker = f'CPU1_TLBI_{nonce}_DONE'
                command = f'echo prove > {path}; cat {path}; echo CPU1_TLBI_{nonce}_"DONE"'
                result = subprocess.run(['python3', str(helper), command, '--until', marker, '--timeout', '50'], stdout=stream, stderr=subprocess.STDOUT)
        finally:
            finish(capture, since)
        if result.returncode:
            raise RuntimeError(f'TLBI capture failed; partial evidence at {capture}; do not retry in this boot')
    evidence = validate(capture.read_text(errors='replace'))
    capture.with_suffix('.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(f'PASS: private CPU1 local page/ASID/full TLBI with stale control. Evidence: {capture}')


if __name__ == '__main__':
    main()

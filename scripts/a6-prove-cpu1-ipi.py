#!/usr/bin/env python3
"""Invoke two tagged CPU1 hardware IPIs once and validate frozen IRQ evidence."""
import argparse
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from a6_cpu1_host_evidence import begin, finish


def validate(text):
    headers = re.findall(r'A6_CPU1_IPI_V1 attempted=(\d+) result=(-?\d+) send_writes=(\d+) release_writes=(\d+)', text)
    if not headers or headers[-1] != ('1', '0', '2', '2'):
        raise RuntimeError('IPI proof failed or incomplete; evidence retained')
    rows = re.findall(r'phase=(\d+) tag=([0-9a-f]{8}) count=(\d+) event=([0-9a-f]{8}) spsr=([0-9a-f]{8}) irq_cpsr=([0-9a-f]{8}) ack=([0-9a-f]{8}) fatal=(\d+)', text)
    final = {int(row[0]): row for row in rows}
    if set(final) != {0, 1}:
        raise RuntimeError('missing IPI phases')
    for phase, tag in enumerate((0xa6c10101, 0xa6c10202)):
        row = final[phase]
        if (int(row[1], 16), int(row[2]), int(row[3], 16), int(row[6], 16), int(row[7])) != (tag, phase + 1, 0x40001, tag, 0):
            raise RuntimeError(f'IPI phase {phase} count/event/tag/fault mismatch')
        if int(row[4], 16) & 0x9f != 0x13 or int(row[5], 16) & 0x9f != 0x92:
            raise RuntimeError('IPI did not enter IRQ mode from IRQ-enabled SVC')
    return {'result': 'pass', 'already_attempted_at_first_status': headers[0][0] == '1',
            'scope': 'two CPU0-to-CPU1 hardware IRQ deliveries, ACK/rearm and tagged publication; no normal Linux SMP or TLB proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decode', type=Path)
    args = parser.parse_args()
    if args.decode:
        capture = args.decode
    else:
        nonce = uuid.uuid4().hex[:12]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        capture = Path('logs/smp') / f'{stamp}-cpu1-ipi-{nonce}.console.txt'
        capture.parent.mkdir(parents=True, exist_ok=True)
        path = '/sys/firmware/a6_cpu1_alias/ipi_proof'
        marker = f'CPU1_IPI_{nonce}_DONE'
        command = f'echo prove > {path}; cat {path}; echo CPU1_IPI_{nonce}_"DONE"'
        helper = Path(__file__).with_name('a6-usb-acm-direct.py')
        since = begin(capture)
        try:
            with capture.open('wb') as stream:
                pre_marker = f'CPU1_IPI_{nonce}_PRE'
                pre_command = f'cat {path}; echo CPU1_IPI_{nonce}_"PRE"'
                before = subprocess.run(['python3', str(helper), pre_command, '--until', pre_marker, '--timeout', '20'], stdout=stream, stderr=subprocess.STDOUT)
                stream.flush()
                if before.returncode:
                    raise RuntimeError(f'pre-call capture failed; no hardware action submitted; evidence at {capture}')
                result = subprocess.run(['python3', str(helper), command, '--until', marker, '--timeout', '30'], stdout=stream, stderr=subprocess.STDOUT)
        finally:
            finish(capture, since)
        if result.returncode:
            raise RuntimeError(f'capture failed; partial evidence at {capture}; do not retry blindly')
    evidence = validate(capture.read_text(errors='replace'))
    capture.with_suffix('.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(f'PASS: two tagged CPU1 IRQ IPIs acknowledged and rearmed. Evidence: {capture}')


if __name__ == '__main__':
    main()

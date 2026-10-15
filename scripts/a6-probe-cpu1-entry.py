#!/usr/bin/env python3
"""One attended CPU1 first-contact call; save and validate frozen evidence."""
import argparse
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from a6_cpu1_host_evidence import begin, finish


def validate(text):
    headers = re.findall(r'A6_CPU1_ENTRY_V1 attempted=\d+[^\r\n]*', text)
    if not headers:
        raise RuntimeError('no CPU1 probe status; retain console and do not retry blindly')
    fields = dict(re.findall(r'(\w+)=([0-9a-f-]+)', headers[-1]))
    for key, expected in {'attempted': '1', 'result': '0', 'magic': 'a6c10001', 'release_writes': '2', 'vector_installed': '1'}.items():
        if fields.get(key) != expected:
            raise RuntimeError(f'CPU1 first contact failed: {key}={fields.get(key)}; evidence retained')
    if fields.get('stage') not in ('2', '3'):
        raise RuntimeError('no valid parked/IRQ-ready entry stage')
    sctlr = int(fields['sctlr'], 16)
    mpidr = int(fields['mpidr'], 16)
    pfr1 = int(fields['pfr1'], 16)
    if sctlr & 0x1005 or (mpidr & 255) != 1 or (pfr1 >> 12) & 15:
        raise RuntimeError('CPU1 marker state violates entry contract')
    return {'result': 'pass', 'fields': fields,
            'already_attempted_at_first_status': 'attempted=1' in headers[0],
            'scope': 'CPU1 owned code entry only; ' + ('private IRQ entry enabled, WFE parked' if fields['stage'] == '3' else 'IRQs masked, WFE parked') + '; no IPI/TLB/SMP scheduling proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decode', type=Path)
    args = parser.parse_args()
    if args.decode:
        capture = args.decode
    else:
        nonce = uuid.uuid4().hex[:12]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        capture = Path('logs/smp') / f'{stamp}-cpu1-entry-{nonce}.console.txt'
        capture.parent.mkdir(parents=True, exist_ok=True)
        path = '/sys/firmware/a6_cpu1_alias/entry_probe'
        marker = f'CPU1_ENTRY_{nonce}_DONE'
        command = f'echo start > {path}; cat {path}; echo CPU1_ENTRY_{nonce}_"DONE"'
        helper = Path(__file__).with_name('a6-usb-acm-direct.py')
        since = begin(capture)
        try:
            with capture.open('wb') as stream:
                pre_marker = f'CPU1_ENTRY_{nonce}_PRE'
                pre_command = f'cat {path}; echo CPU1_ENTRY_{nonce}_"PRE"'
                before = subprocess.run(['python3', str(helper), pre_command, '--until', pre_marker, '--timeout', '20'], stdout=stream, stderr=subprocess.STDOUT)
                stream.flush()
                if before.returncode:
                    raise RuntimeError(f'pre-call capture failed; no hardware action submitted; evidence at {capture}')
                result = subprocess.run(['python3', str(helper), command, '--until', marker, '--timeout', '30'], stdout=stream, stderr=subprocess.STDOUT)
        finally:
            finish(capture, since)
        if result.returncode:
            raise RuntimeError(f'capture failed; partial evidence at {capture}; no blind release retry')
    evidence = validate(capture.read_text(errors='replace'))
    capture.with_suffix('.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(f"PASS: CPU1 published owned-code stage {evidence['fields']['stage']}. Evidence: {capture}")


if __name__ == '__main__':
    main()

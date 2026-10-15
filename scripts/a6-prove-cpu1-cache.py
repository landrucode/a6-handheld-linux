#!/usr/bin/env python3
"""Collect one guarded private CPU1 cache-visibility trial."""
import argparse
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from a6_cpu1_host_evidence import begin, finish


def validate(raw: str) -> dict:
    headers = re.findall(
        r'A6_CPU1_CACHE_V1 attempted=(\d+) result=(-?\d+) sent=(\d+) '
        r'cpu0_hw_pte=([0-9a-f]{8}) cpu1_pte=([0-9a-f]{8}) '
        r'cpu0_sctlr=([0-9a-f]{8}) cpu1_sctlr=([0-9a-f]{8})', raw)
    if len(headers) < 2 or headers[0][:3] != ('0', '0', '0') or \
            headers[-1][:2] != ('1', '0') or headers[-1][2] not in ('3', '36'):
        raise RuntimeError('cache proof absent, failed or incomplete; raw evidence retained')
    pte = int(headers[-1][3], 16)
    cpu1_pte = int(headers[-1][4], 16)
    cpu0 = int(headers[-1][5], 16)
    cpu1 = int(headers[-1][6], 16)
    shared = bool(pte & 0x400)
    if (pte & 0xfffff000) != 0x83ff6000 or \
            (pte & 0x5cc) not in (0x00c, 0x04c, 0x40c, 0x44c) or \
            cpu1_pte not in (0x83ff683e, 0x83ff687e,
                             0x83ff6c3e, 0x83ff6c7e) or \
            (pte & 0x5cc) != (cpu1_pte & 0x5cc) or \
            (cpu0 & (1 << 28)) != (cpu1 & (1 << 28)) or \
            cpu1 & 0x1005 != 5:
        raise RuntimeError('CPU0/CPU1 cached mapping attributes differ')
    if cpu0 & (1 << 28):
        remap = re.findall(
            r'cpu0_prrr=([0-9a-f]{8}) cpu0_nmrr=([0-9a-f]{8})', raw)
        secondary = re.findall(
            r'cpu1_prrr=([0-9a-f]{8}) cpu1_nmrr=([0-9a-f]{8})', raw)
        if not remap or not secondary or \
                remap[-1] != ('ff0a81a8', '40e040e0') or \
                secondary[-1] != remap[-1]:
            raise RuntimeError('TEX-remap registers differ')
    rows = re.findall(
        r'phase=(\d+) tag=([0-9a-f]{8}) cmd=(\d+) count=(\d+) '
        r'event=([0-9a-f]{8}) ack=([0-9a-f]{8}) '
        r'value=([0-9a-f]{8}) fatal=(\d+)', raw)
    final = {int(row[0]): row for row in rows}
    if set(final) != {0, 1, 2}:
        raise RuntimeError('missing cache phase rows')
    values = []
    for phase in range(3):
        row = final[phase]
        tag = 0xa6c50001 + phase
        if (int(row[1], 16), int(row[2]), int(row[3]), int(row[4], 16),
                int(row[5], 16), int(row[7])) != \
                (tag, (6, 5, 6)[phase], phase + 3, 0x40001, tag, 0):
            raise RuntimeError(f'cache phase {phase} tag/IRQ mismatch')
        values.append(int(row[6], 16))
    if values[0] != 0xa6a60011 or values[1] not in (0xa6a60011, 0xb6b60022) \
            or values[2] != 0xb6b60022:
        raise RuntimeError('cache values failed maintained control')
    result = {
        'result': 'pass', 'warm': f'{values[0]:08x}',
        'without_maintenance': f'{values[1]:08x}',
        'after_clean_invalidate': f'{values[2]:08x}',
        'scope': ('one private shareable cached page; no Linux SMP scheduling proof'
                  if shared else
                  'one private non-shareable cached page; no Linux SMP scheduling or shareable coherence proof'),
        'shareable': shared,
    }
    if headers[-1][2] == '36':
        repeated = re.findall(
            r'repeat=32 new=(\d+) stale=(\d+) new_mask=([0-9a-f]{8}) '
            r'stale_mask=([0-9a-f]{8}) last_tag=([0-9a-f]{8}) '
            r'last_value=([0-9a-f]{8})', raw)
        if not repeated:
            raise RuntimeError('repeat profile missing its counters')
        new, stale, new_mask, stale_mask, tag, value = repeated[-1]
        new_bits, stale_bits = int(new_mask, 16), int(stale_mask, 16)
        if int(new) + int(stale) != 32 or new_bits & stale_bits or \
                new_bits | stale_bits != 0xffffffff or \
                new_bits.bit_count() != int(new) or \
                stale_bits.bit_count() != int(stale) or \
                tag != 'a6c60021' or value != 'b6b60022':
            raise RuntimeError('repeat profile counters or final control invalid')
        result.update(repeat_new=int(new), repeat_stale=int(stale),
                      repeat_new_mask=new_mask, repeat_stale_mask=stale_mask,
                      dirty_a_visible=(new_bits & 0x55555555).bit_count())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decode', type=Path)
    args = parser.parse_args()
    if args.decode:
        capture = args.decode
    else:
        nonce = uuid.uuid4().hex[:12]
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        capture = Path('logs/smp') / f'{stamp}-cpu1-cache-{nonce}.console.txt'
        capture.parent.mkdir(parents=True, exist_ok=True)
        path = '/sys/firmware/a6_cpu1_alias/cache_proof'
        helper = Path(__file__).with_name('a6-usb-acm-direct.py')
        since = begin(capture)
        try:
            with capture.open('wb') as stream:
                pre_marker = f'CPU1_CACHE_{nonce}_PRE'
                pre = subprocess.run(
                    ['python3', str(helper), f'cat {path}; echo {pre_marker}',
                     '--until', pre_marker, '--timeout', '20'],
                    stdout=stream, stderr=subprocess.STDOUT)
                stream.flush()
                if pre.returncode:
                    raise RuntimeError(f'pre-call capture failed; no proof sent; {capture}')
                done_marker = f'CPU1_CACHE_{nonce}_DONE'
                command = f'echo prove > {path}; cat {path}; echo {done_marker}'
                result = subprocess.run(
                    ['python3', str(helper), command, '--until', done_marker,
                     '--timeout', '50'], stdout=stream, stderr=subprocess.STDOUT)
        finally:
            finish(capture, since)
        if result.returncode:
            raise RuntimeError(f'cache capture failed; partial evidence at {capture}; do not retry this boot')
    evidence = validate(capture.read_text(errors='replace'))
    capture.with_suffix('.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(f"PASS: private cached-page maintenance, no-maintenance={evidence['without_maintenance']}; evidence: {capture}")


if __name__ == '__main__':
    main()

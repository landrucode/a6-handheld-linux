#!/usr/bin/env python3
"""Summarize captured desktop observation without accessing the phone."""
import argparse
import json
from pathlib import Path
import re


def summarize(path):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', path.read_text())
    blocks = re.split(r'A6_SOAK_SAMPLE=(\d+) uptime=([0-9.]+) [0-9.]+', text)
    samples = []
    problems = []
    prior_timers = [0, 0]
    for offset in range(1, len(blocks), 3):
        index, uptime, block = blocks[offset:offset + 3]
        number = int(index)
        timer0 = re.search(r'^\s+\d+:\s+(\d+)\s+(\d+)\s+A6-AIC\s+162 Edge\s+apple-a6-timer$', block, re.M)
        timer1 = re.search(r'^\s+\d+:\s+(\d+)\s+(\d+)\s+A6-AIC\s+165 Edge\s+apple-a6-timer-cpu1$', block, re.M)
        memory = re.search(r'^MemAvailable:\s+(\d+)', block, re.M)
        power = re.search(r'^vbus_mv=(\d+) vbat_mv=(\d+) tbat_c_candidate=(\d+)', block, re.M)
        auto = re.search(r'^auto=1 .*\bfault=0(?: |$)', block, re.M)
        monitor = re.search(r'^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 .*threshold_mv=3600(?: |$)', block, re.M)
        errors = re.search(r'^\s*Err:\s+(\d+)', block, re.M)
        if not all((timer0, timer1, memory, power, auto, monitor, errors)):
            problems.append({'sample': number, 'reason': 'missing/incorrect required state'})
            continue
        timers = [int(timer0[1]), int(timer1[2])]
        if (int(timer0[2]) or int(timer1[1]) or int(errors[1])
                or any(a <= b for a, b in zip(timers, prior_timers))):
            problems.append({'sample': number, 'reason': 'timer progression/routing or IRQ errors'})
        prior_timers = timers
        samples.append({'sample': number, 'uptime': float(uptime),
                        'timers': timers, 'mem_available_kib': int(memory[1]),
                        'vbus_mv': int(power[1]), 'vbat_mv': int(power[2]),
                        'tbat_candidate_c': int(power[3])})
    numbers = [sample['sample'] for sample in samples]
    if not samples or numbers != list(range(len(samples))):
        problems.append({'reason': 'missing, duplicate or out-of-order samples'})
    markers = re.findall(r'A6_SMP_SOAK_V1 failed[^\r\n]*', text)
    if markers:
        problems.append({'reason': 'worker failure', 'markers': markers})
    wrapped = ('A6_SMP_SOAK_USER_WRAP requested_after_11h' in text
               and 'A6_SMP_SOAK_V1 aborted' in text)
    if 'A6_SMP_SOAK_V1 aborted' in text and not wrapped:
        problems.append({'reason': 'unplanned worker abort'})
    if not re.search(r'^A6_SOAK_COLLECT_END\s*$', text, re.M):
        problems.append({'reason': 'collection completion marker missing'})
    natural = 'A6_SMP_SOAK_V1 completed_samples=1441' in text
    report = {'capture': str(path), 'verdict': 'invalid_or_failed' if problems else 'clean_observed_window',
              'user_wrapped': wrapped, 'natural_24h_completion': natural,
              'samples': len(samples), 'problems': problems,
              'limitation': 'Light desktop plus per-minute per-core hashes; not continuous maximum-load stress.'}
    if samples:
        report.update({'first': samples[0], 'last': samples[-1],
                       'observed_hours': (samples[-1]['uptime'] - samples[0]['uptime']) / 3600,
                       'mem_available_kib_range': [min(s['mem_available_kib'] for s in samples),
                                                   max(s['mem_available_kib'] for s in samples)],
                       'vbat_mv_range': [min(s['vbat_mv'] for s in samples), max(s['vbat_mv'] for s in samples)],
                       'tbat_candidate_c_range': [min(s['tbat_candidate_c'] for s in samples),
                                                  max(s['tbat_candidate_c'] for s in samples)]})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.capture), indent=2))

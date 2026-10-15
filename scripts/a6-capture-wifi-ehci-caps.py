#!/usr/bin/env python3
"""Run the one-shot RAM EHCI capability probe and retain partial evidence."""
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '/sys/firmware/a6_wifi_ehci_caps'


def serial(command):
    marker = 'A6_CAPS_END_' + secrets.token_hex(8)
    return subprocess.run(
        [sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'),
         command + '; echo ' + marker, '--until', marker, '--timeout', '20'],
        capture_output=True, text=True, timeout=30, check=False)


def classify(output):
    lines = [s for s in output.replace('\r', '').splitlines()
             if s.startswith('A6_WIFI_EHCI_CAPS_V1 attempted=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous probe status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if fields.get('attempted') != '1':
        return 'not_run'
    if fields.get('gate_writes') != '2':
        return 'preflight_refused'
    if fields.get('restore') != '0' or fields.get('before') != fields.get('after'):
        return 'restoration_failed'
    return 'caps_pass' if fields.get('result') == '0' else 'probe_refused_restored'


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = ROOT / 'build/session-logs' / (stamp + '-ehci-caps-' + secrets.token_hex(4))
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence = []
    report = {'classification': 'incomplete', 'captured_at_utc': stamp}
    try:
        pre = serial('cat /sys/firmware/a6_charger_policy/status; '
                     'cat /sys/firmware/a6_charger_policy/low_battery_status; '
                     'cat ' + BASE + '/status')
        evidence.append(pre.stdout + pre.stderr)
        if pre.returncode:
            raise RuntimeError('ACM preflight failed')
        auto = re.search(r'(?m)^auto=[^\r\n]*', pre.stdout)
        low = re.search(r'A6_LOW_BATTERY_CANDIDATE_V3[^\r\n]*', pre.stdout)
        for line, required in ((auto, ('auto=1', 'paused=0', 'fault=0', 'attached=1')),
                               (low, ('enabled=1', 'attended_trial=0',
                                      'attended_plugged=0', 'threshold_mv=3600'))):
            if not line or any(not re.search(r'(?:^| )' + f + r'(?: |$)', line.group())
                               for f in required):
                raise RuntimeError('Power protection preflight refused')
        if not re.search(r'(?m)^A6_WIFI_EHCI_CAPS_V1 attempted=0 ', pre.stdout):
            raise RuntimeError('One-shot probe absent or already consumed')
        run = serial('echo read-caps-once-n42 > ' + BASE + '/run; '
                     'echo probe_write_rc=$?; cat ' + BASE + '/status; '
                     'dmesg | busybox grep A6_WIFI_EHCI_CAPS_V1')
        evidence.append(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError('ACM probe capture failed')
        report['classification'] = classify(run.stdout)
        print(report['classification'])
    except subprocess.TimeoutExpired as exc:
        for value in (exc.stdout, exc.stderr):
            evidence.append(value.decode(errors='replace') if isinstance(value, bytes)
                            else value or '')
        report['error'] = 'ACM timeout'
        raise
    except BaseException as exc:
        report['error'] = str(exc)
        raise
    finally:
        prefix.with_suffix('.console.txt').write_text('\n'.join(evidence))
        prefix.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
        print('Evidence: ' + str(prefix.with_suffix('.json')))


if __name__ == '__main__':
    main()

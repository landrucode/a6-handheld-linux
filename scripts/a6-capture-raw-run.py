#!/usr/bin/env python3
"""Run the bounded microphone-bank diagnostic over ACM without provisioning."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy

ROOT=Path(__file__).resolve().parents[1]
os.umask(0o077)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
output=args.output.resolve()
if not output.is_relative_to(ROOT/'build'):
    raise SystemExit('Private capture evidence must stay under build/')
output.mkdir(parents=True,exist_ok=True)
os.environ['A6_ACM_BROKER']=str(ROOT/'build/wifi-native/acm.sock')
provision=runpy.run_path(str(ROOT/'scripts/a6-provision-boot.py'))
phone=provision['module']('phone',ROOT/'scripts/a6-wifi-connect.py').Phone()
try:
    before=phone.checked('test -w /sys/firmware/a6_capture_raw_run && '
        "busybox grep -q 'auto=1 paused=0 fault=0' /sys/firmware/a6_charger_policy/status && "
        "busybox grep -q 'enabled=1 .*triggered=0' /sys/firmware/a6_charger_policy/low_battery_status && "
        'cat /sys/firmware/a6_alsa_status && cat /sys/firmware/a6_charger_policy/status && '
        'cat /sys/firmware/a6_charger_policy/low_battery_status')
    (output/'before.private.log').write_text(before)
    result=phone.checked("printf '%s\\n' recording-banks-raw-restore > /sys/firmware/a6_capture_raw_run; "
        "raw_rc=$?; printf 'RAW_RC=%s\\n' \"$raw_rc\"; "
        'cat /sys/firmware/a6_capture_raw_status; cat /sys/firmware/a6_alsa_status; '
        'cat /sys/firmware/a6_charger_policy/status; cat /sys/firmware/a6_charger_policy/low_battery_status',timeout=90)
    (output/'result.private.log').write_text(result)
    banks=[]
    for m in re.finditer(r'^bank=([0-9a-f]+) error=(-?\d+) cleanup=(-?\d+) elapsed_ns=(\d+) words=(\d+) nonzero=(\d+) status=([0-9a-f]+)/([0-9a-f]+)$',result,re.M):
        bank,error,cleanup,elapsed,words,nonzero,before,after=m.groups()
        banks.append(dict(bank=int(bank,16),error=int(error),cleanup=int(cleanup),elapsed_ns=int(elapsed),words=int(words),nonzero=int(nonzero),status_before=before,status_after=after))
    (output/'analysis.private.json').write_text(json.dumps(banks,indent=2)+'\n')
    print(json.dumps(banks))
    if len(banks)!=2 or any(b['error'] or not b['elapsed_ns'] for b in banks):
        raise SystemExit('Raw acquisition did not complete both banks; private evidence retained')
    if any(b['cleanup'] for b in banks):
        raise SystemExit('Both raw acquisitions completed; final restore failed; private evidence retained')
finally:
    (output/'serial.private.log').write_text('\n'.join(phone.evidence))

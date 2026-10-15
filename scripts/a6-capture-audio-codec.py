#!/usr/bin/env python3
"""Run one bounded codec control probe; cache evidence, never replay a failure."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '/sys/firmware/a6_audio'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', type=Path,
                        default=ROOT/'build/audio-tone-candidate/acm.sock')
    args = parser.parse_args()
    env = os.environ.copy()
    env.pop('A6_USB_HTTP_RPC_TOKEN', None)
    env['A6_ACM_BROKER'] = str(args.broker)
    directory = ROOT/'build/session-logs'/('audio-codec-'+secrets.token_hex(8))
    directory.mkdir(mode=0o700, parents=True)
    fd = os.open(directory/'capture.private.log',
                 os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as log:
        def call(command):
            marker = 'CODEC_END_'+secrets.token_hex(8)
            command += '; printf "\\n%s%s\\n" '+marker[:-4]+' '+marker[-4:]
            result = subprocess.run(
                ['python3', str(ROOT/'scripts/a6-usb-acm-direct.py'), command,
                 '--until', marker, '--timeout', '8'], env=env,
                capture_output=True, text=True, timeout=22)
            log.write(result.stdout+result.stderr)
            log.flush()
            if result.returncode:
                raise RuntimeError('transport failed; codec command never replayed')
            return result.stdout.replace('\r', '')

        before = call('cat '+BASE+'/codec_status '+BASE+'/status')
        if not re.search(r'^A6_AUDIO_CODEC_CONTROL_V1 result=-?\d+ cleanup=0 ',
                         before, re.M):
            raise RuntimeError('codec interface or verified cleanup missing; no run')
        if not re.search(r'^attempted=[01] result=-?\d+ cleanup=0 ', before, re.M):
            raise RuntimeError('MCA cleanup unverified; no run')
        after = call('printf "%s\\n" codec-id-enable-restore > '+BASE+
                     '/codec_run; rc=$?; cat '+BASE+'/codec_status; '
                     'printf "CODEC_WRITE_RC=%s\\n" "$rc"')
        success = bool(re.search(
            r'^A6_AUDIO_CODEC_CONTROL_V1 result=0 cleanup=0 reads=3 control_reads=13$',
            after, re.M) and re.search(r'^CODEC_WRITE_RC=0$', after, re.M))
        health = call('cat /sys/firmware/a6_charger_policy/status '
                      '/sys/firmware/a6_charger_policy/low_battery_status')
        report = {'success': success, 'before': before, 'after': after,
                  'health_after': health, 'codec_output_enabled': False,
                  'transport_replayed': False}
        fd = os.open(directory/'result.private.json',
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
    print(directory.relative_to(ROOT))
    if not success:
        raise SystemExit('codec probe did not complete; inspect cached evidence')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""One explicit audio gate observation via an already-running ACM broker.

Never boot, reset, detach, load modules, replay a failed command or enable an
amp. Preserve partial output privately. Gate changes are restored in-kernel.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '/sys/firmware/a6_audio'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', type=Path, default=ROOT / 'build/wifi-native/acm.sock')
    args = parser.parse_args()
    env = os.environ.copy()
    env.pop('A6_USB_HTTP_RPC_TOKEN', None)
    env['A6_ACM_BROKER'] = str(args.broker)
    path = ROOT / 'build/session-logs' / ('audio-gates-' + secrets.token_hex(8) + '.private.log')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as log:
        def call(command, marker):
            # Split marker so terminal echo cannot satisfy completion.
            command += '; printf "\\n%s%s\\n" ' + marker[:-4] + ' ' + marker[-4:]
            result = subprocess.run(['python3', str(ROOT / 'scripts/a6-usb-acm-direct.py'),
                                     command, '--until', marker, '--timeout', '8'],
                                    env=env, capture_output=True, text=True, timeout=22)
            log.write(result.stdout + result.stderr)
            log.flush()
            if result.returncode:
                raise RuntimeError('transport failed; command not replayed')
            return result.stdout.replace('\r', '')

        try:
            before = call('cat ' + BASE + '/status', 'AUDIO_BEFORE_END')
            if not re.search(r'^attempted=0 result=0 cleanup=0 sampled=0$', before, re.M):
                raise RuntimeError('missing interface or prior attempt; run omitted')
            after = call('printf "%s\\n" snapshot-enable-restore > ' + BASE +
                         '/run; printf "AUDIO_RUN_RC=%s\\n" "$?"; cat ' + BASE + '/status',
                         'AUDIO_RESULT_END')
            if 'AUDIO_RUN_RC=0\n' not in after:
                raise RuntimeError('kernel run failed; inspect retained result, no retry')
            if not re.search(r'^attempted=1 result=0 cleanup=0 sampled=1$', after, re.M):
                raise RuntimeError('snapshot or restoration incomplete; no retry')
            print(after.strip())
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.TimeoutExpired):
                for partial in (error.stdout, error.stderr):
                    if partial:
                        log.write(partial.decode(errors='replace') if isinstance(partial, bytes) else partial)
            print('Observation stopped:', str(error))
            print('Private evidence:', path)
            return 1
    print('Private evidence:', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

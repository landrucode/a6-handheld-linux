#!/usr/bin/env python3
"""Run one cached, zero-only MCA diagnostic through ACM; save and diff snapshots."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '/sys/firmware/a6_audio'
LABELS = ['clocked', 'configured', 'enabled', 'empty', '32-written', '32-wait',
          '64-written', '64-wait', '160-written', '160-wait', 'restored']
EXCLUDED = {0x28, 0x3c}


def diff_snapshots(data, stages=None):
    if len(data) % 4096 or len(data) > 13 * 4096:
        raise ValueError('invalid cached snapshot length')
    snapshots = [struct.unpack('<1024I', data[p:p+4096]) for p in range(0, len(data), 4096)]
    stages = stages if stages is not None else list(range(len(snapshots)))
    if len(stages) != len(snapshots) or any(stage >= len(LABELS) for stage in stages):
        raise ValueError("invalid snapshot stage labels")
    result = []
    for i in range(1, len(snapshots)):
        changes = [{'offset': hex(j*4), 'before': f'{a:08x}', 'after': f'{b:08x}'}
                   for j, (a, b) in enumerate(zip(snapshots[i-1], snapshots[i]))
                   if j*4 not in EXCLUDED and a != b]
        result.append({'before': LABELS[stages[i-1]],
                       'after': LABELS[stages[i]], 'changes': changes})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', type=Path, default=ROOT / 'build/wifi-native/acm.sock')
    parser.add_argument('--tone', action='store_true', help='one explicitly requested bounded tone; no automatic retry')
    parser.add_argument('--level',type=int,choices=range(5),help='reference tone levels: -20,-12,-6,-3,0 dBFS; one second with ramps')
    parser.add_argument('--variant',type=int,choices=range(8),help='matched clock role and GPIO90/91 state')
    parser.add_argument("--probe",action="store_true",help="bounded peak512 monitor probe, stock gain, low/low switches")
    parser.add_argument("--supplies",action="store_true",help="stock VPMON/VBSTMON roles in addition to VMON/IMON")
    parser.add_argument("--reference",action="store_true",help="codec XSP RX-only plus matched amplifier variant, both logs")
    parser.add_argument("--stock44100",action="store_true",help="observed stock44.1k MCA slave and amp master; one bounded burst")
    parser.add_argument("--receiver",action="store_true",help="one bounded B1 codec receiver variant; no amp enable")
    parser.add_argument('--switch-state',type=int,choices=range(4),help='stock44 sweep GPIO90/91 low/high bits')
    parser.add_argument('--all-slots',action='store_true',help='stock44 sweep: same frame sample in all eight slots')
    parser.add_argument('--ios-burst',type=int,choices=(1,2),help='captured playback route without RX; burst2 applies amp overrides after replay')
    args = parser.parse_args()
    if args.ios_burst is not None:
        if args.stock44100 or args.reference or args.receiver or args.probe or args.supplies or args.variant is not None or args.switch_state is not None or args.all_slots or args.level is not None:parser.error('--ios-burst is a standalone captured-state test')
        args.stock44100=True;args.level=4
    if (args.switch_state is not None or args.all_slots) and not args.stock44100:parser.error('switch/all-slot tests require --stock44100')
    if args.all_slots and args.switch_state is None:parser.error('--all-slots requires --switch-state')
    if args.switch_state is not None and args.level is not None:parser.error('switch sweep is fixed to the authorized full-scale peak')
    if args.level is not None and not (args.reference or args.stock44100):parser.error("--level requires --reference")
    if args.stock44100:
        if args.reference or args.receiver or args.probe or args.supplies or args.variant is not None:parser.error("--stock44100 cannot combine with other variants")
        args.tone=True
        if args.level is None:args.level=0
    if args.reference:
        if args.receiver or args.probe or args.supplies:parser.error("--reference cannot combine with receiver or probe")
        args.tone=True
    if args.receiver:
        if args.variant is not None or args.probe or args.supplies:parser.error("--receiver cannot combine with amplifier variants")
        args.tone=True
    if args.supplies:args.probe=True
    if args.probe and (not args.tone or args.variant not in (None,0,4)):parser.error("--probe requires --tone and clock-role variant0 or4")
    if args.variant is not None and not args.tone:parser.error('--variant requires --tone')
    env = os.environ.copy()
    env.pop('A6_USB_HTTP_RPC_TOKEN', None)
    env['A6_ACM_BROKER'] = str(args.broker)
    directory = ROOT / 'build/session-logs' / (('audio-tone-' if args.tone else 'audio-fifo-') + secrets.token_hex(8))
    directory.mkdir(mode=0o700, parents=True)
    fd = os.open(directory / 'capture.private.log', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as log:
        def call(command):
            marker = 'AUDIO_END_' + secrets.token_hex(8)
            command += '; printf "\\n%s%s\\n" ' + marker[:-4] + ' ' + marker[-4:]
            result = subprocess.run(['python3', str(ROOT / 'scripts/a6-usb-acm-direct.py'),
                                     command, '--until', marker, '--timeout', '8'],
                                    env=env, capture_output=True, text=True, timeout=22)
            log.write(result.stdout + result.stderr)
            log.flush()
            if result.returncode:
                raise RuntimeError('transport failed; diagnostic command never replayed')
            return result.stdout.replace('\r', '')

        before = call('cat ' + BASE + '/status'+(' '+BASE+'/codec_status' if args.receiver or args.reference else ''))
        if (args.receiver or args.reference) and not re.search(r'^A6_AUDIO_CODEC_CONTROL_V1 result=-?\d+ cleanup=0 ',before,re.M):
            raise RuntimeError('codec cleanup unverified; no run performed')
        if not re.search(r'A6_AUDIO_FIFO_DISCOVER_V[12]', before) or (not args.tone and not re.search(r'^attempted=0 ', before, re.M)):
            raise RuntimeError('missing fresh interface; no run performed')
        if args.tone and not re.search(r'^attempted=[01] result=-?\d+ cleanup=0 ', before, re.M):
            raise RuntimeError('previous cleanup unverified; no run performed')
        command = 'quiet-tone-enable-restore' if args.tone else 'silent-fifo-enable-restore'
        if args.variant is not None:command='audio-variant-'+str(args.variant)
        if args.receiver:command='codec-receiver-enable-restore'
        if args.reference:command=('codec-amp-level-'+str(args.level)+'-variant-' if args.level is not None else 'codec-amp-variant-')+str(args.variant or 0)
        if args.probe:command=('audio-supply-probe-' if args.supplies else 'audio-probe-')+str(args.variant or 0)
        if args.stock44100:command=('stock-speaker44-sweep-'+str(args.switch_state)+'-allslots-'+str(int(args.all_slots))) if args.switch_state is not None else 'stock-speaker44-level-'+str(args.level)
        if args.ios_burst is not None:command='stock-speaker44-ios-'+str(args.ios_burst)
        after = call('printf "%s\\n" ' + command + ' > ' + BASE +
                     '/run; printf "AUDIO_RUN_RC=%s\\n" "$?"; cat ' + BASE + '/status'+(' '+BASE+'/codec_status' if args.receiver or args.reference else ''))
        if args.tone:
            captures=[(BASE+'/codec_write_readbacks','codec-write-readbacks.private.bin',384*24)] if args.receiver else [(BASE + '/amp_readbacks', 'amp-readbacks.private.bin', 512),
                                       (BASE + '/monitors','monitors.private.bin',3072),
                                       ('/sys/firmware/a6_memory_capture', 'memory-capture.private.bin', 2816)]
            if args.ios_burst is not None:captures=[item for item in captures if item[1]!='monitors.private.bin']
            if args.reference:captures.append((BASE+'/codec_write_readbacks','codec-write-readbacks.private.bin',384*24))
            for remote,name,size in captures:
                data = bytearray()
                for offset in range((size + 511)//512):
                    output = call('printf "\\nAT_BEGIN\\n"; busybox dd if=' + remote +
                                  ' bs=512 skip=' + str(offset) + ' count=1 2>/dev/null | busybox base64; '
                                  'printf "\\nAT_END\\n"')
                    match = re.search(r'\nAT_BEGIN\n([A-Za-z0-9+/=\n]*)\nAT_END\n', output)
                    if not match: raise RuntimeError('bad cached tone framing; never replay')
                    data.extend(base64.b64decode(match[1].replace('\n', ''), validate=True))
                if len(data)>size or (size in (2816,3072) and len(data)!=size):raise RuntimeError('cached tone length')
                target=directory/name;target.write_bytes(data);target.chmod(0o600)
            if args.receiver or args.reference:
                raw=(directory/'codec-write-readbacks.private.bin').read_bytes()
                rows=[struct.unpack('<6I',raw[i:i+24]) for i in range(0,len(raw),24)]
                meta=re.search(r' log_count=(\d+) ',after)
                if not meta or len(rows)!=int(meta[1]):raise RuntimeError('codec register log count mismatch; never replay')
                parsed=[dict(zip(('register','phase','expected','readback','result_u32','samples'),row)) for row in rows]
                target=directory/'codec-write-readbacks.private.json';target.write_text(json.dumps(parsed,indent=2)+'\n');target.chmod(0o600)
            (directory/'status.private.txt').write_text(after)
            (directory/'status.private.txt').chmod(0o600)
        count = re.search(r' snapshots=(\d+) ', after)
        if not count or int(count[1]) > 13:
            raise RuntimeError('missing bounded cached result; no run replay')
        binary = bytearray()
        # Cached reads only. Each small response has framing separate from command echo.
        for offset in range(int(count[1]) * 8):
            output = call('printf "\\nAF_DATA_BEGIN\\n"; busybox dd if=' + BASE +
                          '/dumps bs=512 skip=' + str(offset) + ' count=1 2>/dev/null | busybox base64; '
                          'printf "\\nAF_DATA_END\\n"')
            match = re.search(r'\nAF_DATA_BEGIN\n([A-Za-z0-9+/=\n]+)\nAF_DATA_END\n', output)
            if not match:
                raise RuntimeError('bad cached chunk framing; retain partial evidence')
            chunk = base64.b64decode(match[1].replace('\n', ''), validate=True)
            if len(chunk) != 512:
                raise RuntimeError('short cached chunk')
            binary.extend(chunk)
            target = directory / 'snapshots.private.bin'
            target.write_bytes(binary)
            target.chmod(0o600)
        stage_match = re.search(r"^snapshot_ids=([0-9,]*)$", after, re.M)
        if not stage_match:
            raise RuntimeError("missing snapshot stage labels")
        stages = [int(value) for value in stage_match[1].split(",") if value]
        diff = diff_snapshots(binary, stages)
        summary = {'status': after, 'excluded_data_ports': ['0x28', '0x3c'], 'diffs': diff,
                   'receiver_variant':args.receiver,'codec_reference':args.reference,'stock44100':args.stock44100,'level':args.level,'ios_burst':args.ios_burst,'switch_state':args.switch_state,'all_slots':args.all_slots,
                   'interpretation': 'Changing fields are candidates, not proven occupancy. '
                   'TX overflow=0x2000, underrun=0x1000; faults may require W1C acknowledgement.'}
        target = directory / 'result.private.json'
        target.write_text(json.dumps(summary, indent=2) + '\n')
        target.chmod(0o600)
        print(after.strip())
        for row in diff:
            print(row['before'] + ' -> ' + row['after'] + ': ' +
                  ', '.join(c['offset'] + '=' + c['before'] + '->' + c['after'] for c in row['changes']))
        print('Private evidence:', directory)
        health=call('cat /sys/firmware/a6_charger_policy/status /sys/firmware/a6_charger_policy/low_battery_status')
        summary['health_after']=health
        target.write_text(json.dumps(summary,indent=2)+'\n')
        if 'AUDIO_RUN_RC=0\n' not in after or not re.search(r' result=0 cleanup=0 ', after):
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

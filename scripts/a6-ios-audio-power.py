#!/usr/bin/env python3
"""Read-only stock iOS power/service snapshots; owner controls playback.

Capture idle, playing, then idle-again in one iOS session. Diff results are
correlations, not proof of rail ownership. Raw device data stays in build/.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import plistlib
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ('AppleCS35L19Amp', 'AppleCS42L65Audio', 'AppleAE2Audio',
           'AppleAE2MCA', 'AppleAE2IIS', 'AppleAE2IOP', 'AppleARMIO',
           'AppleARMPMU', 'AppleARMPMUCharger', 'AppleS5L8960XPMGR')


def flatten(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, path + (str(index),))
    else:
        # Preserve plist types; JSON is used only for the diff report.
        yield path, value


def capture(args):
    os.umask(0o077)
    folder = ROOT / 'build/session-logs/ios-audio-power' / args.session
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = {'label': args.label, 'samples': []}
    for sample in range(args.samples):
        entry = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
        requests = [('ioreg', plane) for plane in ('IOPower', 'IOService')]
        requests += [('ioregentry', name) for name in ENTRIES]
        for operation, name in requests:
            path = folder / f'{args.label}-{sample}-{name}.plist'
            # Do not overwrite evidence or silently substitute another plane.
            if path.exists():
                raise SystemExit(f'Already exists: {path}')
            command = ['idevicediagnostics']
            if args.udid:
                command += ['-u', args.udid]
            run = subprocess.run(command + [operation, name], capture_output=True, timeout=30)
            try:
                parsed = plistlib.loads(run.stdout)
            except plistlib.InvalidFileException:
                parsed = None
            valid = (run.returncode == 0 and isinstance(parsed, dict)
                     and parsed.get('Status', 'Success') == 'Success'
                     and bool(parsed.get('IORegistry')))
            entry[name] = {'available': valid, 'returncode': run.returncode}
            if not valid:
                # Empty planes/missing providers are explicit missing evidence.
                path.with_suffix('.response.private.bin').write_bytes(run.stdout)
                continue
            path.write_bytes(run.stdout)
            entry[name]['path'] = str(path)
        if not all(entry[name]['available'] for name in ('AppleCS35L19Amp', 'AppleCS42L65Audio')):
            raise SystemExit('Required amp/codec entries unavailable; capture incomplete')
        entry['ended_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        report['samples'].append(entry)
    destination = folder / f'{args.label}.private.json'
    if destination.exists():
        raise SystemExit(f'Already exists: {destination}')
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(destination)


def diff(args):
    before = dict(flatten(plistlib.loads(args.before.read_bytes())))
    after = dict(flatten(plistlib.loads(args.after.read_bytes())))
    changes = []
    for path in sorted(before.keys() | after.keys()):
        if path not in before or path not in after or before[path] != after[path]:
            changes.append({'path': list(path), 'before_present': path in before,
                            'after_present': path in after, 'before': repr(before.get(path)),
                            'after': repr(after.get(path))})
    print(json.dumps({'warning': 'List positions may change; verify entry identity in raw trees. '
                      'Changes are candidates, not identified rails. Compare repeated samples '
                      'and idle-again to reject background changes.', 'changes': changes}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    grab = commands.add_parser('capture')
    grab.add_argument('session')
    grab.add_argument('label', choices=('idle', 'playing', 'idle-again'))
    grab.add_argument('--samples', type=int, choices=range(1, 6), default=3)
    grab.add_argument('--udid')
    compare = commands.add_parser('diff')
    compare.add_argument('before', type=Path)
    compare.add_argument('after', type=Path)
    args = parser.parse_args()
    if args.command == 'capture':
        if not args.session or not all(c.isascii() and (c.isalnum() or c in '-_') for c in args.session):
            parser.error('session must contain only ASCII letters, digits, - or _')
        capture(args)
    else:
        diff(args)


if __name__ == '__main__':
    main()

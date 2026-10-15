#!/usr/bin/env python3
"""Generate private mic replay from the owner's decoded recording snapshot."""
import argparse
import json
import os
import re
from pathlib import Path

os.umask(0o077)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('snapshot', type=Path)
parser.add_argument('--all-banks', action='store_true', help='Replay every captured bank, excluding immutable identity registers 1..5')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
data = json.loads(args.snapshot.read_text())
codec = {}
for start, encoded in data['properties']['AppleCS42L65Audio'].items():
    codec.update({int(start) + i: value for i, value in enumerate(bytes.fromhex(encoded))})
if codec.get(5) != 0xb1:
    raise SystemExit('Recording codec revision is not B1')
profile = (root / 'build/audio-research/codec-receiver-sequence.private.inc').read_text()
match = re.search(r'a6_ac_profile_registers\[\]=\{(.*?)\}', profile)
registers = [int(v, 0) for v in match[1].split(',')]
# Stock recording also changes power control 0x0f, outside the receiver profile.
# Apply it last, after the captured routing and input state is established.
if 0x0f not in registers:
    registers.append(0x0f)
if args.all_banks:
    registers = sorted(reg for reg in codec if reg > 5)
    # Establish routing before the recording power control.
    registers.remove(0x0f)
    registers.append(0x0f)
if len(registers) > 768 or any(r not in codec for r in registers):
    raise SystemExit('Recording snapshot lacks a replay register')
output = root / 'build/audio-research/mic-recording-sequence.private.inc'
output.write_text('/* Owner stock recording state; private, never commit. */\n'
                  'static const u32 a6_mic_codec_regs[]={' +
                  ','.join(hex(r) for r in registers) + '};\n'
                  'static const u8 a6_mic_codec_values[]={' +
                  ','.join(str(codec[r]) for r in registers) + '};\n')
output.chmod(0o600)
print(f'Prepared {len(registers)} captured mic register values privately')

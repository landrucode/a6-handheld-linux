#!/usr/bin/env python3
"""Read the retained one-shot USB reply into private ignored host files.

This reads RAM snapshots only; it never submits a USB Wi-Fi transfer or trial.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '/sys/firmware/a6_wifi_ehci_enum'


def offsets(data, needle):
    return [i for i in range(len(data) - len(needle) + 1)
            if data[i:i + len(needle)] == needle]


def analyze(data):
    printable = sum(32 <= value <= 126 for value in data)
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'broadcast_offsets': offsets(data, b'\xff' * 6),
            'ethertype_886c_offsets': offsets(data, bytes.fromhex('886c')),
            'broadcom_oui_offsets': offsets(data, bytes.fromhex('001018')),
            'frame_control_8000_offsets': offsets(data, bytes.fromhex('8000')),
            'printable_ascii_bytes': printable,
            'printable_ascii_fraction': printable / len(data) if data else 0}


def loopback_tx(variant=1):
    """Exact fixed diagnostic frame, independently reconstructed for comparison."""
    if variant not in (1, 2, 3):
        raise ValueError("unsupported diagnostic payload variant")
    size = 80 if variant == 1 else 96
    data = bytearray(size)
    data[0:2] = (0xa001).to_bytes(2, 'little')
    data[4:6] = size.to_bytes(2, 'little')
    data[6:8] = (1 if variant == 1 else 2).to_bytes(2, 'little')
    total = sum(int.from_bytes(data[i:i+2], 'little') for i in range(0, 16, 2))
    total = (total & 65535) + (total >> 16)
    total = (total & 65535) + (total >> 16)
    data[2:4] = ((~total) & 65535).to_bytes(2, 'little')
    data[16] = 0x20
    data[26:38] = b'A6USBLOOP01!' if variant == 1 else b'A6USBLOOP02!'
    data[38:] = bytes(i ^ (0x5a if variant == 1 else 0xa5) for i in range(38, size))
    if variant == 3:
        data[2] ^= 1
    return bytes(data)


def analyze_loopback(data, variant=1):
    tx = loopback_tx(variant)
    flags = int.from_bytes(data[:2], 'little') if len(data) >= 2 else None
    declared = int.from_bytes(data[4:6], 'little') if len(data) >= 6 else None
    total = sum(int.from_bytes(data[i:i+2], 'little') for i in range(0, 16, 2)) if len(data) >= 16 else None
    if total is not None:
        total = (total & 65535) + (total >> 16)
        total = (total & 65535) + (total >> 16)
    present = bool(flags is not None and flags & 0x8000)
    body = data[16:] if present and len(data) >= 16 else data if not present else b''
    expected = tx[16:]
    return {'header_present': present,
            'flags': format(flags, '04x') if flags is not None else None,
            'kind': (flags >> 12) & 7 if present else None,
            'declared_bytes': declared if present else None, 'transfer_bytes': len(data),
            'length_matches': declared == len(data) if present else None,
            'checksum_valid': total == 65535 if present else None, 'body_bytes': len(body),
            'tx_sha256': hashlib.sha256(tx).hexdigest(),
            'whole_frame_equal': data == tx, 'payload_equal': body == expected,
            'payload_match_offsets_in_reply': offsets(data, expected),
            'reply_body_match_offsets_in_tx_payload': offsets(expected, body) if body else [],
            'body_has_expected_prefix': body.startswith(expected),
            'body_has_expected_suffix': body.endswith(expected),
            'tag_offsets': offsets(data, tx[26:38]),
            'pattern_offsets': offsets(data, expected[22:]),
            'tx_variant': variant, 'whole_tx_match_offsets': offsets(data, tx)}


def parse_capture(console, marker, loopback=False):
    lines = console.replace('\r', '').splitlines()
    begin, end = marker + '_BEGIN', marker + '_END'
    if lines.count(begin) != 1 or lines.count(end) != 1:
        raise ValueError('missing or ambiguous snapshot markers')
    start, stop = lines.index(begin), lines.index(end)
    if stop <= start:
        raise ValueError('reversed snapshot markers')
    statuses = [line for line in lines[:start]
                if line.startswith('A6_WIFI_USB_BULK_RX_V1 ')]
    if len(statuses) != 1:
        raise ValueError('missing or ambiguous receive status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', statuses[0]))
    required = {'enabled': '1', 'attempted': '1', 'submitted': '1',
                'usb_result': '0', 'registered': '1', 'deregistered': '1',
                'claimed': '1', 'disconnected': '1', 'release': '0', 'tx': '1' if loopback else '0'}
    if any(fields.get(key) != value for key, value in required.items()):
        raise ValueError('receive or cleanup not verified')
    if loopback:
        loop_lines = [line for line in lines[:start]
                      if line.startswith('A6_WIFI_USB_LOOPBACK_V1 ')]
        if len(loop_lines) != 1:
            raise ValueError('missing or ambiguous loopback status')
        loop = dict(re.findall(r'(\w+)=([^ ]+)', loop_lines[0]))
        required_loop = {'enabled': '1', 'attempted': '1', 'out': '1',
                         'restore': '0', 'before': '0', 'after': '0', 'ctl_tx': '4', 'ctl_rx': '4'}
        if any(loop.get(k) != v for k, v in required_loop.items()):
            raise ValueError('loopback capture or mode restoration not verified')
        if not 1 <= int(loop.get('in', '0')) <= 16:
            raise ValueError('invalid loopback receive count')
        length = int(loop['bytes'])
    else:
        length = int(fields['bytes'])
    if not 1 <= length <= (32864 if loopback else 2048):
        raise ValueError('invalid snapshot length')
    payload = ''.join(lines[start + 1:stop])
    data = base64.b64decode(payload, validate=True)
    if len(data) != length:
        raise ValueError('snapshot length differs from completed receive')
    if loopback:
        packets = split_journal(data)
        if not (1 <= len(packets) <= int(loop['in'])):
            raise ValueError('journal count differs from bounded receives')
    return data


def split_journal(data):
    """Length-prefixed completed receives, including rejected headers/bodies."""
    packets, cursor = [], 0
    while cursor < len(data):
        if len(packets) == 16 or len(data) - cursor < 6:
            raise ValueError('invalid journal count or truncated length')
        length = int.from_bytes(data[cursor:cursor+2], 'little')
        cursor += 6
        if length > 2048 or length > len(data) - cursor:
            raise ValueError('invalid journal packet length')
        packets.append(data[cursor:cursor+length])
        cursor += length
    return packets


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/session-logs')
    parser.add_argument('--loopback', action='store_true', help='read retained loopback reply; never rerun the trial')
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if not destination.is_relative_to(ROOT / 'build'):
        parser.error('private packet files must stay under ignored build/')
    relative = destination.relative_to(ROOT)
    ignored = subprocess.run(['git', 'check-ignore', '-q', str(relative / 'probe')], cwd=ROOT)
    if ignored.returncode:
        parser.error('destination must be ignored by git')
    destination.mkdir(parents=True, exist_ok=True)
    marker = 'A6_RX_PRIVATE_' + secrets.token_hex(8)
    def emit(value):
        split = len(value) // 2
        return "printf '%s%s\\n' " + value[:split] + ' ' + value[split:]
    command = (f'cat {BASE}/bulk_rx; ' +
               (f'cat {BASE}/loopback; ' if args.loopback else '') + emit(marker + '_BEGIN') +
               f'; busybox base64 {BASE}/bulk_rx_data; ' + emit(marker + '_END'))
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'),
                             command, '--until', marker + '_END', '--timeout', '20'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    prefix = destination / ('wifi-rx-packet-' + marker[-16:])
    private_write(prefix.with_suffix('.console.private.txt'), result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('snapshot read failed; private console preserved')
    data = parse_capture(result.stdout.decode('ascii', errors='strict'), marker, loopback=args.loopback)
    private_write(prefix.with_suffix('.private.bin'), data)
    dump = '\n'.join(f'{i:04x}  ' + data[i:i+16].hex(' ')
                     for i in range(0, len(data), 16)) + '\n'
    private_write(prefix.with_suffix('.hex.private.txt'), dump.encode())
    summary = analyze(data)
    if args.loopback:
        packets = split_journal(data)
        cursor = 0
        times = []
        for packet in packets:
            times.append(int.from_bytes(data[cursor+2:cursor+6], 'little'))
            cursor += 6 + len(packet)
        summary['loopback_packets'] = [dict(analyze(packet), arrival_ms=when, loopback=analyze_loopback(packet), loopback_variant2=analyze_loopback(packet, 2), loopback_bad_checksum=analyze_loopback(packet, 3)) for packet, when in zip(packets, times)]
        for index, packet in enumerate(packets):
            private_write(prefix.with_suffix(f'.rx{index}.private.bin'), packet)
        private_write(prefix.with_suffix('.tx.private.bin'), loopback_tx())
        private_write(prefix.with_suffix('.tx2.private.bin'), loopback_tx(2))
        private_write(prefix.with_suffix('.tx-bad.private.bin'), loopback_tx(3))
    private_write(prefix.with_suffix('.analysis.json'),
                  (json.dumps(summary, indent=2) + '\n').encode())
    print(json.dumps({'analysis': summary, 'private_prefix': str(prefix)}, indent=2))


if __name__ == '__main__':
    main()

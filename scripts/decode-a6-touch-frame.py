#!/usr/bin/env python3
"""Validate a captured N42 Z2 wire frame and decode contact records locally."""
import argparse
import json
from pathlib import Path
import re


def decode(wire: bytes) -> dict:
    if not 31 <= len(wire) <= 838:
        raise ValueError('wire length outside bounds')
    if wire[0] not in (0xea, 0xeb) or wire[1] not in (1, 2):
        raise ValueError('unexpected command or sequence')
    length = int.from_bytes(wire[2:4], 'little')
    if length + 5 != len(wire) or sum(wire[:5]) & 255:
        raise ValueError('invalid header length/checksum')
    payload = wire[5:-2]
    if sum(payload) & 65535 != int.from_bytes(wire[-2:], 'little'):
        raise ValueError('invalid payload checksum')
    header, count, stride = payload[2], payload[16], payload[17]
    if payload[0] not in (0x43, 0x44) or not 24 <= header <= len(payload):
        raise ValueError('unsupported payload header')
    if count > 10 or (count and (stride < 30 or count > (len(payload)-header)//stride)):
        raise ValueError('contact records outside payload bounds')
    contacts, seen = [], set()
    for i in range(count):
        record = payload[header+i*stride:header+(i+1)*stride]
        identifier = record[0]
        if identifier in seen:
            raise ValueError('duplicate contact ID')
        seen.add(identifier)
        contacts.append({'id': identifier, 'state': record[1],
                         'x_raw': int.from_bytes(record[4:6], 'little', signed=True),
                         'y_raw': int.from_bytes(record[6:8], 'little', signed=True)})
    return {'wire_bytes': len(wire), 'sequence': wire[1], 'type': payload[0],
            'header_bytes': header, 'record_bytes': stride, 'contacts': contacts}


def selftest():
    payload = bytearray(84)
    payload[0], payload[2], payload[16], payload[17] = 0x44, 24, 2, 30
    payload[24], payload[25], payload[54], payload[55] = 1, 3, 2, 4
    payload[28:30], payload[30:32] = (123).to_bytes(2, 'little'), (456).to_bytes(2, 'little')
    def packet(p):
        length = len(p)+2
        header = bytearray((0xea, 1, length & 255, length >> 8, 0))
        header[4] = (-sum(header)) & 255
        return bytes(header+p+(sum(p)&65535).to_bytes(2, 'little'))
    wire = packet(payload)
    assert len(decode(wire)['contacts']) == 2
    invalid = [wire[:n] for n in range(len(wire))]
    invalid += [wire+b'\x00', bytes((wire[0]^1,))+wire[1:]]
    for index, value in ((2, 255), (16, 11), (17, 29), (54, 1)):
        changed = payload.copy()
        changed[index] = value
        invalid.append(packet(changed))
    damaged = bytearray(wire)
    damaged[30] ^= 1
    invalid.append(bytes(damaged))
    for bad in invalid:
        try:
            decode(bad)
        except ValueError:
            continue
        raise AssertionError('malformed packet accepted')
    print('PASS two-contact fixture; truncation, checksum, header, count, stride and duplicate-ID rejection')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', nargs='?', type=Path)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    if args.selftest:
        selftest()
    elif args.capture:
        text = args.capture.read_text().replace('\r', '')
        match = re.search(r'^frame=([0-9a-f]+)$', text, re.M)
        if not match:
            raise SystemExit('no captured frame: native contacts remain unproven')
        print(json.dumps(decode(bytes.fromhex(match[1])), indent=2))
    else:
        parser.error('provide a capture or --selftest')

#!/usr/bin/env python3
"""Select stock WLAN files from bounded private OTP evidence, without exposing it."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def vers1(data):
    """Strict CIS tuple framing, then version-1 chip/RF product strings."""
    if not data or len(data) > 512:
        raise ValueError('OTP size outside accepted bounds')
    offset = 0
    versions = []
    ended = False
    while offset < len(data):
        tag = data[offset]
        if tag == 0xff:
            if any(x not in (0, 0xff) for x in data[offset+1:]):
                raise ValueError('nonpadding after CIS end')
            ended = True
            break
        if tag == 0:
            offset += 1
            continue
        if offset + 2 > len(data):
            raise ValueError('truncated tuple header')
        length = data[offset+1]
        end = offset + 2 + length
        if end > len(data):
            raise ValueError('truncated tuple payload')
        payload = data[offset+2:end]
        if tag == 0x15:
            if len(payload) < 5 or payload[:2] != bytes((8, 0)) or payload[-1] != 0xff:
                raise ValueError('unexpected VERS1 version/framing')
            strings = payload[2:-1].split(b'\0')
            if len(strings) != 5 or strings[-1] or strings[2] or strings[3]:
                raise ValueError('unexpected VERS1 product strings')
            versions.append(tuple(x.decode('ascii') for x in strings[:2]))
        offset = end
    if not ended or len(versions) != 1:
        raise ValueError('missing/ambiguous VERS1 or CIS terminator')
    return versions[0]


def tokens(string):
    result = []
    for token in re.split(r'[ ,]+', string):
        if not re.fullmatch('[A-Za-z]=[A-Za-z0-9.]+', token) or token in result:
            raise ValueError('invalid or repeated product token')
        result.append(token)
    if len({x.split('=')[0] for x in result}) != len(result):
        raise ValueError('ambiguous product token key')
    return result


def select(data, metadata):
    chip, rf = vers1(data)
    chip_tokens, rf_tokens = tokens(chip), tokens(rf)
    shim = next(x for x in metadata if x['CFBundleIdentifier'] ==
                'com.apple.driver.AppleBCMWLANBusInterfaceHSICShim')
    products = shim['IOKitPersonalities']['4334']['HSICProductInfo']
    matches = [(name, value) for name, value in products.items()
               if set(value.get('HSICChipInfo', ())) <= set(chip_tokens)
               and set(value.get('HSICRFHardwareInfo', ())) <= set(rf_tokens)
               and value.get('HSICChipInfo') and value.get('HSICRFHardwareInfo')]
    if len(matches) != 1:
        raise ValueError('stock product selection missing or ambiguous')
    name, product = matches[0]
    default = product['FilesDB']['default']
    if (name != 'Heineken - 4334B3 - TDK' or product['vendor-id'] != 'TDK' or
        default != {'Firmware': '4334b1/centennial.trx', 'NVRAM': '4334b1/heineken-t-st.txt'}):
        raise ValueError('unexpected product; this candidate is scoped to measured N42')
    return {'chip_tokens': chip_tokens, 'rf_tokens': rf_tokens,
            'stock_product': name, 'vendor': product['vendor-id'],
            'default_files': default, 'otp_sha256': hashlib.sha256(data).hexdigest(),
            'otp_bytes': len(data), 'device_mac_selected': False,
            'limitation': 'CIS product match only; default file key and MAC provenance still need verification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('otp', type=Path)
    args = parser.parse_args()
    path = args.otp.resolve()
    if not path.is_relative_to(ROOT/'build'):
        raise ValueError('private OTP must remain under ignored build/')
    metadata = (ROOT/'build/touch-research/ios10-wifi-kexts/prelink.json').read_bytes()
    if hashlib.sha256(metadata).hexdigest() != '47876dce87e0a1f6987bab8363a97723b6293cce5dac45be2b5ee60990d0d1f5':
        raise ValueError('stock metadata hash mismatch')
    print(json.dumps(select(path.read_bytes(), json.loads(metadata)), indent=2))


if __name__ == '__main__':
    main()

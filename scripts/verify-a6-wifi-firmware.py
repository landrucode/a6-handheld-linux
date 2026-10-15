#!/usr/bin/env python3
"""Verify local stock centennial firmware; never upload it or select NVRAM."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

REPO = Path(__file__).resolve().parents[1]
FILES = {
    'centennial.trx': (454656, '9448d4559945275d1f5a4e43bc4aa6ff676476e7d305b353010974aab205e60b'),
    'centennial.clm_bin': (4844, '2b4981bab1c7502b0c2b09ffcec32a2996a70bf187a0cf187e0d377780645698'),
    'centennial.clmb': (4640, '5bd20ed23926edd6caf3cc2f65ce7756ff82b10693ddef622c993af9a3f61802'),
    'heineken-m-mm.txt': (1779, '6f69d6352750df18b41bb1aaef79612acc1923045b28dfd728bde323b8cbc775'),
    'heineken-m-ms.txt': (1828, '5bbe1896c3beecf705d190f803aa3cab31419ee55418a406de046fa3c7ff3c75'),
    'heineken-t-st.txt': (1863, 'eb7744de010c2c032221fd22777186afba0411195e0f705e26f506b33a6663c8'),
    'heineken-u-st.txt': (1792, 'e0f553b76a275c52d5bb6a3ab947410fa842c08fa6161759ca561b105a8ad99b'),
}


def verify_trx(data):
    if len(data) < 28:
        raise ValueError('short TRX header')
    magic, length, crc, flags, download, second, third = struct.unpack_from('<7I', data)
    if magic != 0x30524448 or length != len(data):
        raise ValueError('invalid TRX magic/length')
    if not flags & 0x20 or not 28 <= download + 28 <= length:
        raise ValueError('invalid uncompressed download length')
    if (~zlib.crc32(data[12:length]) & 0xffffffff) != crc:
        raise ValueError('TRX CRC mismatch')
    return {'file_bytes': length, 'flag_version': hex(flags),
            'crc32': hex(crc), 'download_length_field': download,
            'header_plus_download_bytes': download + 28,
            'remaining_bytes': length - download - 28,
            'other_offset_words': [hex(second), hex(third)],
            'linux_usb_header_check': 'compatible; hardware download not tested'}


def stock_selection():
    path = REPO / 'build/touch-research/ios10-wifi-kexts/prelink.json'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != '47876dce87e0a1f6987bab8363a97723b6293cce5dac45be2b5ee60990d0d1f5':
        raise ValueError('unexpected stock metadata; reproduce the documented extraction')
    entry = next(e for e in json.loads(data)
                 if e['CFBundleIdentifier'] == 'com.apple.driver.AppleBCMWLANBusInterfaceHSICShim')
    products = entry['IOKitPersonalities']['4334']['HSICProductInfo']
    result = []
    for name, product in products.items():
        if name.startswith('CENTENNIAL'):
            default = product['FilesDB']['default']
            if default['Firmware'] != '4334b1/centennial.trx':
                raise ValueError('unexpected centennial firmware mapping')
            result.append({'name': name, 'chip_match': product['HSICChipInfo'],
                           'rf_match': product['HSICRFHardwareInfo'],
                           'vendor': product['vendor-id'], 'default_files': default})
    if len(result) != 3:
        raise ValueError('unexpected centennial selection table')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract', action='store_true',
                        help='Extract fixed stock files from the existing local HFS image')
    args = parser.parse_args()
    output = REPO / 'build/touch-research/ios10-wifi-firmware'
    tool = REPO / '.deps/legacy-ios-kit/bin/linux/x86_64/hfsplus'
    image = REPO / 'build/touch-research/ios10-rootfs.hfs'
    if args.extract:
        if hashlib.sha256(tool.read_bytes()).hexdigest() != '38042c8d6702e62293e8fe078a1caaa88124171fa851b9d8bef72eaf8191416f':
            raise ValueError('unexpected HFS extractor')
        output.mkdir(parents=True, exist_ok=True)
    report = []
    for name, (size, digest) in FILES.items():
        path = output / name
        if args.extract:
            data = subprocess.check_output(
                [str(tool), str(image), 'cat', '/usr/share/firmware/wifi/4334b1/' + name],
                timeout=30)
        else:
            data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('unexpected stock file: ' + name)
        if args.extract:
            path.write_bytes(data)
        report.append({'name': name, 'bytes': size, 'sha256': digest})
    trx = verify_trx((output / 'centennial.trx').read_bytes())
    print(json.dumps({'files': report, 'trx': trx, 'stock_selection': stock_selection(),
                      'hardware_tested': False,
                      'nvram_selected': False,
                      'limitation': 'No board calibration, device MAC, upload or radio operation.'},
                     indent=2))


if __name__ == '__main__':
    main()

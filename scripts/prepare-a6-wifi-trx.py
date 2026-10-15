#!/usr/bin/env python3
"""Pack the measured N42 TDK firmware privately with the pinned Cascadia helper."""
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pack(firmware, nvram, mac, helper):
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', mac):
        raise ValueError('invalid MAC format')
    address = bytes.fromhex(mac.replace(':', ''))
    if address[0] & 1 or address == bytes(6):
        raise ValueError('invalid unicast MAC')
    if len(firmware) < 28:
        raise ValueError('short TRX')
    magic, length, crc, flags, download, second, third = struct.unpack_from('<7I', firmware)
    if (magic != 0x30524448 or length != len(firmware) or third or
        not flags & 0x20 or not 28 <= 28+download <= length or
        helper.trx_crc(firmware) != crc or any(firmware[28+download:])):
        raise ValueError('unexpected input TRX or nonzero trailer')
    # Preserve every stock calibration/country value; inject only missing MAC.
    if any(re.match(r'\s*macaddr\s*=', line.split('#', 1)[0]) for line in nvram.splitlines()):
        raise ValueError('stock NVRAM already contains a MAC')
    blob = helper.nvram_blob(nvram, mac.lower())
    image = bytearray(firmware[:28+download] + blob)
    struct.pack_into('<I', image, 4, len(image))
    struct.pack_into('<I', image, 24, len(blob))
    struct.pack_into('<I', image, 8, helper.trx_crc(image))
    words = (len(blob)-4)//4
    if struct.unpack_from('<I', blob, len(blob)-4)[0] != ((~words & 65535)<<16 | words):
        raise ValueError('bad NVRAM token')
    if blob[:-4].count(('macaddr='+mac.lower()).encode()+b'\0') != 1:
        raise ValueError('MAC injection not unique')
    return bytes(image), len(blob)


def main():
    fwcheck = load(ROOT/'scripts/verify-a6-wifi-firmware.py', 'fwcheck')
    fwdir = ROOT/'build/touch-research/ios10-wifi-firmware'
    for name, (size, digest) in fwcheck.FILES.items():
        data = (fwdir/name).read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('stock firmware hash mismatch: '+name)
    selection = load(ROOT/'scripts/verify-a6-wifi-otp-selection.py', 'selection')
    metadata = (ROOT/'build/touch-research/ios10-wifi-kexts/prelink.json').read_bytes()
    if hashlib.sha256(metadata).hexdigest() != '47876dce87e0a1f6987bab8363a97723b6293cce5dac45be2b5ee60990d0d1f5':
        raise ValueError('stock selection metadata hash mismatch')
    measured = selection.select((ROOT/'build/session-logs/20261001-wifi-otp.private.bin').read_bytes(), json.loads(metadata))
    helper_path = ROOT/'.deps/cascadia-wifi-reference/scripts/trx-add-nvram.py'
    if hashlib.sha256(helper_path.read_bytes()).hexdigest() != '8fbb0ce07651546c392e1aabc96561b8937df9ff713d2782f9aa6d30fd6b724b':
        raise ValueError('packing helper hash mismatch')
    helper = load(helper_path, 'cascadia_pack')
    records = []
    for path in (ROOT/'build/host/lockdown').glob('*.plist'):
        record = plistlib.loads(path.read_bytes())
        if isinstance(record.get('WiFiMACAddress'), str):
            records.append((path, record['WiFiMACAddress']))
    if len(records) != 1:
        raise ValueError('cached MAC absent or ambiguous')
    pairing, mac = records[0]
    image, nvram_bytes = pack((fwdir/'centennial.trx').read_bytes(),
                              (fwdir/'heineken-t-st.txt').read_text(encoding='ascii'), mac, helper)
    digest = hashlib.sha256(image).hexdigest()
    output = ROOT/'build/wifi-firmware'/('centennial-tdk-'+digest[:8]+'.trx')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() != image:
        raise ValueError('existing package mismatch')
    if not output.exists():
        output.write_bytes(image)
        output.chmod(0o400)
    report = {'output':str(output.relative_to(ROOT)), 'sha256':digest, 'bytes':len(image),
              'nvram_bytes':nvram_bytes, 'stock_product':measured['stock_product'],
              'mac_source':'one cached host iOS pairing record; ownership unverified',
              'factory_mac_verified':False, 'mac_injected':True,
              'association_allowed':False, 'firmware_execution_tested':False,
              'country_calibration':'stock values unchanged',
              'packing_helper_sha256':hashlib.sha256(helper_path.read_bytes()).hexdigest()}
    manifest = output.with_suffix('.json')
    text = json.dumps(report,indent=2)+'\n'
    if manifest.exists():
        if manifest.read_text() != text:
            raise ValueError('existing package provenance mismatch')
    else:
        manifest.write_text(text)
        manifest.chmod(0o400)
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()

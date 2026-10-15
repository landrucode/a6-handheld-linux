#!/usr/bin/env python3
"""Verify the fixed stock BCM4334 read-only OTP protocol offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    kernel = (ROOT / 'build/touch-research/Kernelcache-ios10.raw').read_bytes()
    digest = hashlib.sha256(kernel).hexdigest()
    assert digest == 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'scripts/extract-a6-stock-touch.py')
    extract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extract)
    path = ROOT / 'build/touch-research/ios10-wifi-kexts/com.apple.driver.AppleBCMWLANBusInterfaceHSIC-analysis.macho'
    blob = path.read_bytes()
    def segments(data):
        return [struct.unpack_from('<IIII', c, 24) for k, c in extract.commands(data) if k == 1]
    def read(data, address, length):
        matches = [o + address - v for v, _, o, n in segments(data)
                   if v <= address and address + length <= v + n]
        assert len(matches) == 1
        return data[matches[0]:matches[0] + length]
    def word(address):
        assert read(blob, address, 4) == read(kernel, address, 4)
        return struct.unpack('<I', read(blob, address, 4))[0]
    ins = {}
    for start, end in ((0x80c21dd4, 0x80c21df2), (0x80c21f5c, 0x80c21fa8),
                       (0x80c22132, 0x80c2215a), (0x80c29134, 0x80c292ea)):
        assert read(blob, start, end-start) == read(kernel, start, end-start)
        output = subprocess.check_output(['llvm-objdump', '-d', '--triple=thumbv7-apple-ios',
            f'--start-address={start:#x}', f'--stop-address={end:#x}', str(path)], text=True)
        for line in output.splitlines():
            m = re.match(r'^([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+(.+)$', line)
            if m:
                ins[int(m[1], 16)] = re.sub(r'\s+', ' ', m[2]).split(' @ ', 1)[0].strip()
    expected = {
        0x80c22132: 'movw r2, #0x4334',
        0x80c22138: 'beq 0x80c22152 <__text+0xbca>',
        0x80c22154: 'bl 0x80c21f5c <__text+0x9d4>',
        0x80c21f76: 'add r0, pc', 0x80c21f78: 'adds r0, #0x8',
        0x80c21f7a: 'str r0, [r4]',
        0x80c21dd4: 'cmp r1, #0x2',
        0x80c21dde: 'add r0, pc', 0x80c21de0: 'ldr.w r0, [r0, r1, lsl #2]',
        0x80c2913a: 'ldr r2, [r1, #0x48]', 0x80c2913c: 'movs r1, #0x2',
        0x80c29142: 'movs r0, #0xc1', 0x80c29148: 'movs r0, #0x11',
        0x80c2914e: 'strh.w r4, [sp, #0x1a]',
        0x80c29152: 'lsr.w r0, r4, #0x10',
        0x80c29156: 'strh.w r0, [sp, #0x1c]', 0x80c2915a: 'movs r0, #0x10',
        0x80c291da: 'ldr r0, [sp, #0x34]', 0x80c291e6: 'movs r1, #0x1',
        0x80c2924a: 'ubfx r0, r0, #0x3, #0xd',
        0x80c29250: 'ubfx r6, r1, #0x3, #0xd',
        0x80c29254: 'subs r0, r0, r6', 0x80c29268: 'movne.w r4, #0x200',
        0x80c29284: 'movs r1, #0x0', 0x80c29288: 'add r6, r0',
        0x80c29298: 'movs r0, #0xc1', 0x80c2929e: 'movs r0, #0x11',
        0x80c292b0: 'movs r0, #0x10', 0x80c292cc: 'ldr r0, [sp, #0x34]',
        0x80c292ce: 'strh.w r0, [sp, #0x16]', 0x80c292da: 'movs r2, #0x2',
        0x80c292e2: 'adds r6, #0x2',
    }
    for address, text in expected.items():
        assert ins.get(address) == text, (hex(address), ins.get(address))
    vtable = word(0x80c21fa4) + 0x80c21f76 + 4 + 8
    assert word(vtable + 0x48) == 0x80c21dd5
    table = word(0x80c21de8) + 0x80c21dde + 4
    addresses = [word(table + 4*i) for i in range(3)]
    assert addresses == [0x18000800, 0x18000838, 0x1800083a]
    print(json.dumps({'kernel_sha256': digest, 'chip': '0x4334',
        'chip_dispatch_verified': True, 'otp_slot_dispatch_verified': True,
        'type': '0xc1', 'request': '0x11', 'reply_bytes': 16,
        'data_word': 3, 'value': 'address low16', 'index': 'address high16',
        'otp_base': hex(addresses[0]), 'start_register': hex(addresses[1]),
        'end_register': hex(addresses[2]), 'range_bits': [3, 13],
        'stock_max_bytes': 512, 'stride_bytes': 2,
        'hardware_tested': False, 'limitation': 'ROM availability and RF tuple still unmeasured.'}, indent=2))


if __name__ == '__main__':
    main()

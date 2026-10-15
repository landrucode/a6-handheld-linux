#!/usr/bin/env python3
"""Verify stock HSIC ready/reset dispatch offline; do not program GPIOs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    data = (ROOT / 'build/touch-research/Kernelcache-ios10.raw').read_bytes()
    assert hashlib.sha256(data).hexdigest() == 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'scripts/extract-a6-stock-touch.py')
    extract = importlib.util.module_from_spec(spec); spec.loader.exec_module(extract)
    segments = [struct.unpack_from('<IIII', c, 24) for k, c in extract.commands(data) if k == 1]
    def read(blob, segs, address, length):
        matches = [(o + address - v) for v, _, o, n in segs if v <= address and address + length <= v + n]
        assert len(matches) == 1
        return blob[matches[0]:matches[0]+length]
    def word(address):
        return struct.unpack('<I', read(data, segments, address, 4))[0]
    instructions = {}
    sources = (
        ('ios10-clock-dependencies/com.apple.driver.AppleARMPlatform-analysis.macho',
         ((0x80596c58, 0x80596c88),)),
        ('ios10-usb-map-kexts/com.apple.driver.AppleUSBHSIC-analysis.macho',
         ((0x80c15510, 0x80c15524), (0x80c17d78, 0x80c17d90),
          (0x80c14c4c, 0x80c14c64), (0x80c18414, 0x80c18446),
          (0x80c187da, 0x80c18810))),
        ('ios10-wifi-kexts/com.apple.driver.AppleBCMWLANBusInterfaceHSIC-analysis.macho',
         ((0x80c2a4a0, 0x80c2a4b2),)),
        ('ios10-usb-map-kexts/com.apple.driver.AppleS5L8930XUSB-analysis.macho',
         ((0x80e45e9c, 0x80e45ee6),)),
        ('ios10-usb-map-kexts/com.apple.driver.AppleS5L8930XUSBPhy-analysis.macho',
         ((0x80f9f524, 0x80f9f530), (0x80f9f674, 0x80f9f682))),
        ('ios10-usb-map-kexts/com.apple.driver.AppleS5L8930XUSBHSIC-analysis.macho',
         ((0x80f80394, 0x80f80400), (0x80f80556, 0x80f80566))),
        ('ios10-power-dependencies/com.apple.driver.AppleD1972PMU-analysis.macho',
         ((0x810e7678, 0x810e7686), (0x810e7858, 0x810e794c),
          (0x810e897c, 0x810e899c))),
    )
    for name, ranges in sources:
        path = ROOT / 'build/touch-research' / name; blob = path.read_bytes()
        segs = [struct.unpack_from('<IIII', c, 24) for k, c in extract.commands(blob) if k == 1]
        for start, end in ranges:
            assert read(blob, segs, start, end-start) == read(data, segments, start, end-start)
            text = subprocess.check_output(['llvm-objdump', '-d', '--triple=thumbv7-apple-ios',
                f'--start-address={start:#x}', f'--stop-address={end:#x}', str(path)], text=True)
            for line in text.splitlines():
                m = re.match(r'^([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+(.+)$', line)
                if m: instructions[int(m[1], 16)] = re.sub(r'\s+', ' ', m[2]).split(' @ ', 1)[0].strip()
    expected = {
        0x810e7678: 'cmp r1, #0xb',
        0x810e767a: 'add.w r0, r1, #0x68',
        0x810e898c: 'ldrb r3, [r3, #0xd]',
        0x810e78d6: 'and r0, r0, #0x1d',
        0x810e7904: 'orr r0, r0, #0x2',
        0x810e7914: 'eor r0, r0, #0x2',
        0x80596c6a: 'ldr.w r4, [r0, #0x1e8]',
        0x80c1551a: 'str.w r0, [r4, #0x2a0]',
        0x80c17d78: 'ldr.w r0, [r4, #0x280]',
        0x80c17d82: 'ldr r6, [r1, #0x3c]',
        0x80c187da: 'movs r0, #0x1',
        0x80c187de: 'ldr.w r0, [r4, #0x2a0]',
        0x80c187f6: 'str.w r11, [sp, #0x3c]',
        0x80c1880a: 'movs r0, #0x64',
        0x80c14c56: 'ldr r3, [r3, #0x58]',
        0x80c14c5c: 'ldr.w r12, [r0, #0x448]',
        0x80c18426: 'mov r10, r6',
        0x80c1843c: 'mov.w r11, #0x0',
        0x80c2a4a6: 'ldr.w r3, [r1, #0x340]',
        0x80c2a4aa: 'movs r1, #0x2',
        0x80c2a4ac: 'mov.w r2, #0x1f4',
        0x80e45ee0: 'orr.w r1, r1, r5',
        0x80f803ce: 'ldr.w r10, [r0]',
        0x80f803fc: 'movs r4, #0x0',
        0x80f8055a: 'mov r0, r10',
        0x80f8055c: 'mov r1, r4',
        0x80f9f526: 'ldr.w r3, [r0, #0x368]',
        0x80f9f52c: 'movs r2, #0x20',
        0x80f9f676: 'ldr.w r3, [r0, #0x36c]',
        0x80f9f67c: 'mvn r2, #0x20',
    }
    for address, expected_text in expected.items():
        assert instructions.get(address) == expected_text, hex(address)
    wrapper = word(0x80596b78) + 0x80596b1c + 4 + 8
    assert word(wrapper + 0x3c) == 0x80596c59
    specialized = word(0x80f8021c) + 0x80f80212 + 4 + 8
    assert word(specialized + 0x468) == 0x80c181cd
    assert word(specialized + 0x474) == 0x80c17c79
    device_vtable = word(0x80c14268) + 0x80c1425e + 4 + 8
    assert word(device_vtable + 0x340) == 0x80c14c4d
    assert word(specialized + 0x448) == 0x80c181a5
    # Action 2's jump-table entry reaches the traced pulse branch.
    assert 0x80c183e2 + read(data, segments, 0x80c183e4, 1)[0] * 2 == 0x80c18414
    # PHY selector 4 reaches bit 5; selector 3, not 4, uses bit 2.
    assert 0x80f9f4e0 + read(data, segments, 0x80f9f4e4, 1)[0] * 2 == 0x80f9f524
    assert 0x80f9f62a + read(data, segments, 0x80f9f62e, 1)[0] * 2 == 0x80f9f674
    assert word(0x80f80d64 + 4 + 0x2b8) & ~1 == 0x8095dee4
    assert word(0x80fa009c + 0x368) == 0x80f9f35b
    assert word(0x80fa009c + 0x36c) == 0x80f9f351
    # No inherited phy-port override: stock takes WLAN's literal port 4.
    tree_spec = importlib.util.spec_from_file_location('tree', ROOT / 'scripts/inspect-a6-platform-tree.py')
    tree = importlib.util.module_from_spec(tree_spec); tree_spec.loader.exec_module(tree)
    topology = json.loads(subprocess.check_output([sys.executable, str(ROOT / 'scripts/verify-a6-wifi-topology.py')], text=True))
    for source in topology['sources']:
        nodes = tree.parse_tree((ROOT / source['source']).read_bytes())
        assert not any('phy-port' in props or 'phy-id' in props for props in nodes.values())
    for source in topology['sources']:
        reset = source['functions']['function-device_reset']
        assert reset['pin_word'] == '0xa' and reset['flags_raw'] == '01000100'
    print(json.dumps({'kernel_sha256': hashlib.sha256(data).hexdigest(),
        'host_ready_dispatch_verified': True, 'reset_wrapper_dispatch_verified': True,
        'reset_electrical_polarity_verified': True,
        'reset_pmu_register': '0x72', 'reset_request_one_bit1': 0,
        'reset_request_zero_bit1': 1,
        'device_to_port_action_dispatch_verified': True,
        'wlan_reset_pulse_ms': 500, 'wlan_reset_settle_ms': 100,
        'phy_port4_powerdown_mask': '0x20',
        'phy_global_transition_safe_for_live_gadget_verified': False,
        'reset_provider_register_sequence_verified': False,
        'complete_port_state_sequence_verified': False,
        'hardware_writes': 0}, indent=2))


if __name__ == '__main__': main()

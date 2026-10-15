#!/usr/bin/env python3
"""Check stock N42 clock dispatch offline; output derived addresses, never write MMIO."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SHA = 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
KEXT_SHA = '282169637accffa96a7fd44d17ee524f5fc69179b8b541b98ba252b697c17d90'


def main():
    topology = json.loads(subprocess.check_output(
        ['python3', str(ROOT / 'scripts/verify-a6-wifi-topology.py')], text=True))
    kernel = (ROOT / 'build/touch-research/Kernelcache-ios10.raw').read_bytes()
    if hashlib.sha256(kernel).hexdigest() != KERNEL_SHA:
        raise ValueError('stock kernel checksum changed')
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'scripts/extract-a6-stock-touch.py')
    extract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extract)
    segments = [struct.unpack_from('<IIII', c, 24)
                for kind, c in extract.commands(kernel) if kind == 1]

    # Decode the personality from the pinned kernel itself, not a loose
    # extracted JSON file. Apple's plist uses shared ID/IDREF elements.
    prelink = next(c for kind, c in extract.commands(kernel)
                   if kind == 1 and c[8:24].rstrip(b'\0') == b'__PRELINK_INFO')
    _, _, offset, size = struct.unpack_from('<IIII', prelink, 24)
    xml = ET.fromstring(kernel[offset:offset+size].rstrip(b'\0'))
    ids = {e.attrib['ID']: e for e in xml.iter() if 'ID' in e.attrib}

    def decode(element, depth=0):
        if depth > 128:
            raise ValueError('recursive stock plist')
        if 'IDREF' in element.attrib:
            return decode(ids[element.attrib['IDREF']], depth + 1)
        if element.tag == 'dict':
            children = list(element)
            if len(children) % 2 or any(e.tag != 'key' for e in children[::2]):
                raise ValueError('malformed stock dictionary')
            return {children[i].text: decode(children[i+1], depth+1)
                    for i in range(0, len(children), 2)}
        if element.tag == 'array':
            return [decode(e, depth+1) for e in element]
        return element.text

    info = decode(xml if xml.tag == 'dict' else xml[0])
    phy_bundle = next(e for e in info['_PrelinkInfoDictionary']
                      if e['CFBundleIdentifier'] == 'com.apple.driver.AppleS5L8930XUSBPhy')
    personality = phy_bundle['IOKitPersonalities']['AppleS5L8930XUSBPhy']
    assert personality['IOProviderClass'] == 'AppleARMIODevice'
    assert personality['IONameMatch'] == 'otgphyctrl,s5l8930x'

    def raw(address, count):
        for base, _, offset, size in segments:
            if base <= address and address + count <= base + size:
                return kernel[offset + address - base:offset + address - base + count]
        raise ValueError('address outside file-backed stock kernel')

    def word(address):
        return struct.unpack('<I', raw(address, 4))[0]

    original = ROOT / 'build/touch-research/ios10-clock-dependencies/com.apple.driver.AppleS5L8950X.macho'
    analysis = original.with_name(original.stem + '-analysis.macho')
    if hashlib.sha256(original.read_bytes()).hexdigest() != KEXT_SHA:
        raise ValueError('stock platform driver checksum changed')
    # Check the analysis text against the original pinned kernel as well as
    # the original extraction: an analysis file is not independently trusted.
    instructions = {}
    ranges = ((0x8114ccc0, 0x8114ccf0), (0x8114ce42, 0x8114ce94),
              (0x8114d8d0, 0x8114db44), (0x8114db44, 0x8114dce8),
              (0x8114ea12, 0x8114eaaa), (0x8114ee70, 0x8114ee90))
    extra_ranges = (
        ('ios10-clock-dependencies/com.apple.driver.AppleARMPlatform-analysis.macho',
         ((0x80599ff8, 0x8059a028), (0x8059a0a4, 0x8059a108),
          (0x8059a320, 0x8059a3c2), (0x8059ef98, 0x8059f086))),
        ('ios10-usb-map-kexts/com.apple.driver.AppleEmbeddedUSB-analysis.macho',
         ((0x80960520, 0x809606cc), (0x809606cc, 0x8096074c))),
        ('ios10-usb-map-kexts/com.apple.driver.AppleS5L8930XUSB-analysis.macho',
         ((0x80e46330, 0x80e46594), (0x80e465ac, 0x80e46752))),
        ('ios10-usb-map-kexts/com.apple.driver.AppleS5L8930XUSBPhy-analysis.macho',
         ((0x80f9ec94, 0x80f9ecb2), (0x80f9f344, 0x80f9f37e))),
    )
    checked_ranges = []
    for source, source_ranges in ((analysis, ranges), *(
            (ROOT / 'build/touch-research' / name, rs) for name, rs in extra_ranges)):
        data = source.read_bytes()
        source_segments = [struct.unpack_from('<IIII', c, 24)
                           for kind, c in extract.commands(data) if kind == 1]
        for start, end in source_ranges:
            matching = [(base, offset) for base, _, offset, size in source_segments
                        if base <= start and end <= base + size]
            if len(matching) != 1:
                raise ValueError('ambiguous analysis code mapping')
            base, offset = matching[0]
            if data[offset+start-base:offset+end-base] != raw(start, end-start):
                raise ValueError('analysis code differs from pinned stock kernel')
            checked_ranges.append((start, end))
            text = subprocess.check_output(
                ['llvm-objdump', '-d', '--triple=thumbv7-apple-ios',
                 f'--start-address={start:#x}', f'--stop-address={end:#x}', str(source)], text=True)
            for line in text.splitlines():
                match = re.match(r'^([0-9a-f]+):\s+(?:[0-9a-f]{4}\s+)+(.+)$', line)
                if match:
                    instructions[int(match[1], 16)] = re.sub(r'\s+', ' ', match[2]).split(' @ ', 1)[0].strip()

    def require(address, expected):
        if instructions.get(address) != expected:
            raise ValueError(f'clock trace instruction changed at {address:#x}')

    require(0x8114ccca, 'add r1, pc')
    require(0x8114cccc, 'adds r1, #0x8')
    require(0x8114ccce, 'str r1, [r0]')
    vtable = word(0x8114ccd4) + 0x8114ccca + 4 + 8
    assert vtable == 0x81150d80
    slots = {0x350: 0x8059ef99, 0x3dc: 0x8114d8d1, 0x3e0: 0x8114db45,
             0x488: 0x8114ea13, 0x490: 0x8114ee71, 0x494: 0x8114ee79}
    for slot, target in slots.items():
        assert word(vtable + slot) == target
    require(0x8114da6c, 'adds r0, #0xc')
    require(0x8114da74, 'ldrb r3, [r0, r1]')
    require(0x8114d9ea, 'add.w r0, r10, #0x10')
    require(0x8114d9f6, 'ldrb r3, [r0, r1]')
    require(0x8114dc7e, 'mov.w r1, #0x140')
    require(0x8114dc82, 'add.w r5, r1, r0, lsl #2')
    require(0x8114dc90, 'orr r2, r0, #0x80000000')
    require(0x8114dcb4, 'tst.w r0, #0x40000000')
    require(0x8114ea28, 'mov.w r0, #0x1000')
    require(0x8114ea2c, 'add.w r5, r0, r11, lsl #2')
    require(0x8114ea76, 'movw r0, #0x10f')
    require(0x8114ea9a, 'eor.w r0, r0, r0, lsr #4')
    require(0x8114ee70, 'ldr.w r0, [r0, #0x550]')
    require(0x8114ee74, 'ldr r0, [r0, r1]')
    require(0x8114ee78, 'ldr.w r0, [r0, #0x550]')
    require(0x8114ee7c, 'str r2, [r0, r1]')
    # Resource zero supplies both accessors above; resource one is separate.
    require(0x8114ce4e, 'movs r1, #0x0')
    require(0x8114ce62, 'movs r1, #0x1')
    require(0x8114ce82, 'str.w r0, [r4, #0x550]')
    require(0x8114ce90, 'str.w r0, [r4, #0x554]')
    # USB mask bits select ordinal client lists, then the provider's
    # clock-gates u32 array translates that ordinal to a logical PMGR ID.
    require(0x80960728, 'lsl.w r0, r5, r4')
    require(0x8096072c, 'tst.w r0, r8')
    require(0x80960732, 'ldr.w r0, [r10, r4, lsl #2]')
    require(0x80960626, 'ldr.w r3, [r1, #0x354]')
    require(0x8096067c, 'mov r2, r6')
    helper_vtable = (word(0x8059a024) + 0x8059a00e + 4 + 8) & 0xffffffff
    assert helper_vtable == 0x805c8b5c
    assert word(helper_vtable + 0x354) == 0x8059a0a5
    assert raw((word(0x8059a490) + 0x8059a394 + 4) & 0xffffffff, 12) == b'clock-gates\0'
    require(0x8059a00e, 'add r0, pc')
    require(0x8059a010, 'adds r0, #0x8')
    require(0x8059a012, 'str r0, [r4]')
    require(0x8059a3b4, 'lsrs r0, r0, #0x2')
    require(0x8059a3b6, 'str r0, [r4, #0x5c]')
    require(0x8059a3c0, 'str r0, [r4, #0x60]')
    require(0x8059a0f0, 'ldr.w r3, [r2, #0x350]')
    require(0x8059a0f4, 'ldr.w r1, [r1, r5, lsl #2]')
    require(0x8059f044, 'ldr.w r3, [r0, #0x3dc]')
    require(0x8059f054, 'blx r3')
    require(0x8059f06c, 'ldr.w r3, [r0, #0x3e0]')
    require(0x8059f076, 'blx r3')
    # The shared USB controller holds separate clients for high mask bits.
    require(0x80e46416, 'tst.w r8, #0x10000')
    require(0x80e4641c, 'ldr.w r0, [r4, #0x110]')
    require(0x80e464dc, 'tst.w r8, #0x20000')
    require(0x80e464e2, 'ldr.w r0, [r4, #0x114]')
    require(0x80e46544, 'ldr r1, [r0]')
    require(0x80e46546, 'bic r1, r1, #0x20')
    require(0x80e46624, 'ldr r0, [pc, #0x144]')
    require(0x80e4662a, 'ldr.w r3, [r0, #0x34c]')
    require(0x80e46634, 'blx r3')
    require(0x80e466e8, 'orr r1, r1, #0x20')
    # The PHY's register helpers use its own resource-zero mapping.
    require(0x80f9ec94, 'ldr r0, [r4, #0x7c]')
    require(0x80f9ec98, 'ldr.w r3, [r1, #0x1fc]')
    require(0x80f9ec9c, 'movs r1, #0x0')
    require(0x80f9ecb0, 'str r0, [r4, #0x78]')
    require(0x80f9f344, 'ldr r0, [r0, #0x78]')
    require(0x80f9f346, 'str r2, [r0, r1]')
    tree_spec = importlib.util.spec_from_file_location('adt', ROOT / 'scripts/inspect-a6-platform-tree.py')
    adt = importlib.util.module_from_spec(tree_spec)
    tree_spec.loader.exec_module(adt)
    tree = adt.parse_tree((ROOT / '.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw').read_bytes())
    io = '/device-tree/arm-io'
    assert struct.unpack('<III', tree[io]['ranges']) == (0, 0x30000000, 0x10000000)
    pmgr_regs = struct.unpack('<16I', tree[io + '/pmgr']['reg'])
    assert pmgr_regs[:2] == (0x0f100000, 0x7000)
    base = 0x30000000 + pmgr_regs[0]
    gates = struct.unpack('<8I', tree[io + '/usb-complex']['clock-gates'])
    mask = int.from_bytes(tree[io + '/usb-complex/usb-ehci/wlan']['clock-mask'], 'little')
    selected = [gate for bit, gate in enumerate(gates) if mask & (1 << bit)]
    assert selected == [0x36, 0x3a]
    usb_ctl = int.from_bytes(tree[io + '/usb-complex']['usb_ctl'], 'little')
    assert usb_ctl == 0x24
    phy = tree[io + '/otgphyctrl']
    assert b'otgphyctrl,s5l8930x' in phy['compatible'].split(b'\0')
    assert struct.unpack('<II', phy['reg']) == (0x06000000, 0x1000)
    assert int.from_bytes(phy['clock-mask'], 'little') == 0x60010
    records = topology['usb_clock_records']
    primary = records['0x36'][2]
    secondary = records['0x3a'][3]
    ehci_secondary = records['0x36'][3]
    print(json.dumps({
        'stock_kernel_sha256': KERNEL_SHA,
        'record_layout': 'shared 44-byte records; byte lists at +12 and +16',
        'stock_dispatch_checked': True,
        'wlan_mask_positional_selection_verified': True,
        'wlan_selected_logical_ids': [hex(gate) for gate in selected],
        'usb_ctl_property_mask': hex(usb_ctl),
        'phy_resource_zero_from_tree': '0x36000000',
        'phy_provider_personality_association_verified': True,
        'pmgr_resource_zero': hex(base),
        'ehci_primary_index': hex(primary),
        'ehci_primary_register': hex(base + 0x1000 + primary * 4),
        'ehci_secondary_index': hex(ehci_secondary),
        'ehci_secondary_register': hex(base + 0x140 + ehci_secondary * 4),
        'phy1_secondary_index': hex(secondary),
        'phy1_secondary_register': hex(base + 0x140 + secondary * 4),
        'primary_update': 'preserve except 0x10f; low nibble target; poll low/high nibbles equal',
        'secondary_update': 'preserve other bits; request bit31; poll bit30 clear',
        'hardware_tested': False,
        'shared_usb_sequence_complete': False,
        'trace_ranges_sha256': {f'{start:#x}-{end:#x}': hashlib.sha256(raw(start, end-start)).hexdigest()
                                for start, end in checked_ranges},
    }, indent=2))


if __name__ == '__main__':
    main()

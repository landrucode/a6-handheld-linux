#!/usr/bin/env python3
"""Verify offline N42 audio evidence anchors; never access a device or emit firmware."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def import_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--research', type=Path, default=ROOT / 'build/audio-research')
    parser.add_argument('--tree', type=Path, default=ROOT / 'build/touch-research/DeviceTree-ios10.raw')
    parser.add_argument('--kernel', type=Path, default=ROOT / 'build/touch-research/Kernelcache-ios10.raw')
    args = parser.parse_args()
    tree = import_script('inspect-a6-audio-tree').inventory(args.tree.read_bytes())
    if tree['source_sha256'] != '9dfa77a3e1db226a304abb643dc829ed2e7d305beebfdc67d965eb255837736d':
        raise ValueError('expected stock 14G61 N42 tree')
    nodes = tree['nodes']
    full_tree = import_script('inspect-a6-platform-tree').parse_tree(args.tree.read_bytes())
    for key in ('aea-power-provider', 'external-power-provider'):
        assert not any(key in props for props in full_tree.values()), key
    prefix = '/device-tree/arm-io/'
    expected_clocks = {'spi3': (29, 60, '0x3f1010f0'), 'i2c0': (41, 70, '0x3f101118'),
                       'i2s0': (105, 41, '0x3f1010a4'), 'i2s1': (106, 42, '0x3f1010a8'),
                       'i2s2': (107, 43, '0x3f1010ac'), 'mca0': (110, 56, '0x3f1010e0'),
                       'mca1': (108, 44, '0x3f1010b0'), 'ae2': (104, 0, None)}
    for name, (logical, index, physical) in expected_clocks.items():
        record = nodes[prefix + name]['pmgr_clock_records'][0]
        assert (record['logical_id'], record['register_index'], record['pmgr_physical']) == (logical, index, physical)
    for name, tx, rx in [('i2s0', 0x34190010, 0x34190038), ('i2s1', 0x34191010, 0x34191038),
                         ('i2s2', 0x34192010, 0x34192038), ('mca0', 0x34196028, 0x3419603c),
                         ('mca1', 0x34197028, 0x3419703c)]:
        n = nodes[prefix + name]
        assert n['dma-parent']['path'] == prefix + 'cdma'
        assert [r['fifo_physical'] for r in n['dma_records']] == [hex(tx), hex(rx), hex(tx), hex(rx)]
    assert nodes[prefix + 'mca0/audio-speaker']['compatible'] == ['audio-data,cs35l19']
    assert nodes[prefix + 'mca0']['function-pclk_gate']['cells_after_handle'] == ['0x61647657', '0x5']
    assert nodes[prefix + 'i2c0/audio-speaker']['function-ext_master']['target'] == prefix + 'mca0/audio-codec-reference'
    assert nodes[prefix + 'i2c0/audio-speaker']['function-mclk_control']['target'] == prefix + 'i2s2/audio-bluetooth'

    commands = import_script('extract-a6-stock-touch').commands
    loaded = {}
    if not 28 <= args.kernel.stat().st_size <= 128 * 1024 * 1024:
        raise ValueError('unexpected stock kernelcache size')
    loaded['stock-kernel'] = args.kernel.read_bytes()
    assert hashlib.sha256(loaded['stock-kernel']).hexdigest() == 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
    for directory in ('ios10', 'platform', 'firmware-kexts'):
        manifest = json.loads((args.research / directory / 'manifest.json').read_text())
        assert manifest['source_sha256'] == 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
        for item in manifest['kexts']:
            data = (args.research / directory / (item['bundle'] + '.macho')).read_bytes()
            assert hashlib.sha256(data).hexdigest() == item['sha256']
            loaded[item['bundle']] = data

    def vm_bytes(bundle, addr, count):
        data = loaded[bundle]
        for kind, command in commands(data):
            if kind == 1:
                base, _, offset, size = struct.unpack_from('<IIII', command, 24)
                if base <= addr and addr + count <= base + size:
                    start = offset + addr - base
                    return data[start:start + count]
        raise ValueError('VM range outside file-backed segments')

    amp = 'com.apple.driver.AppleCS35L19Amp'
    table = {hex(slot): hex(struct.unpack('<I', vm_bytes(amp, 0x80db5110 + slot, 4))[0] & ~1)
             for slot in (0x580, 0x584, 0x588, 0x598, 0x59c, 0x5a0)}
    assert table == {'0x580': '0x80a38df8', '0x584': '0x80a392f8', '0x588': '0x80a38f2c',
                     '0x598': '0x80a392bc', '0x59c': '0x80a3938e', '0x5a0': '0x80db37b4'}
    # Exact instruction anchors after resolving image VM/file mappings.
    anchors = [
        ('com.apple.driver.AppleEmbeddedAudio', 0x80a339ac, '2cd0', 'absent aea power provider skips resolution'),
        ('com.apple.driver.AppleEmbeddedAudio', 0x80a33e84, '1dd0', 'absent external power provider skips setup'),
        ('com.apple.driver.AppleA5AE2', 0x805edef2, '0161', 'ACS clock-enable store'),
        ('com.apple.driver.AppleA5AE2', 0x805edf0c, '0161', 'ACS clock-disable store'),
        ('com.apple.driver.AppleSamsungI2S', 0x811a5338, '4160', 'I2S mode +4'),
        ('com.apple.driver.AppleSamsungI2S', 0x811a533a, '0463', 'I2S RX format +0x30'),
        ('com.apple.driver.AppleSamsungI2S', 0x811a55ac, '8160', 'I2S TX control +8'),
        ('com.apple.driver.AppleSamsungI2S', 0x811a55bc, '4163', 'I2S RX control +0x34'),
        ('com.apple.driver.AppleAE2Audio', 0x810c15d2, '50f82540', 'MCA indexed read *4'),
        ('com.apple.driver.AppleAE2Audio', 0x810c169a, '40f82580', 'MCA indexed write *4'),
    ]
    # Revision-specific stop commands and labelled TX fault tests.
    anchors += [
        (amp, 0x80db383c, 'b0284cd3', 'ID comparison b0 followed by unsigned-below branch'),
        ('stock-kernel', 0x811a4ba0, '81604163', 'MCLK-only clears TX and RX stream controls'),
        ('stock-kernel', 0x811a5052, '0620c0f2f810', 'version3 stream-control base 01f80006'),
        ('stock-kernel', 0x811a572a, '42f48070', 'MCLK nclk divide-by-two selection'),
        ('stock-kernel', 0x811a573c, 'c4f8bc00', 'MCLK clock-control shadow write'),
        ('stock-kernel', 0x811a4bae, '41f02001', 'MCLK-only global enable bit'),
        ('com.apple.driver.AppleAE2Audio', 0x810c0abe, '4ff48072', 'revision 0 TX stop command 0x100'),
        ('com.apple.driver.AppleAE2Audio', 0x810c0b64, '0122', 'revision 1 TX stop command 1'),
        ('com.apple.driver.AppleAE2Audio', 0x810c152c, '15f4005f', 'TX overflow mask 0x2000'),
        ('com.apple.driver.AppleAE2Audio', 0x810c155e, '15f4805f', 'TX underflow mask 0x1000'),
        ('com.apple.driver.AppleAE2Audio', 0x810c1044, 'dbf89c00', 'FIFO depth calculation loads cached RX capacity'),
        ('com.apple.driver.AppleAE2Audio', 0x810c1052, 'dbf89800', 'FIFO depth calculation loads cached TX capacity'),
        ('com.apple.driver.AppleAE2Audio', 0x810c1094, '28f00305', 'FIFO depth calculation rounds configured threshold'),
        ('com.apple.driver.AppleAE2Audio', 0x810c10c6, '2846', 'FIFO depth returns computed threshold, not MMIO occupancy'),
        ('com.apple.driver.AppleAE2Audio', 0x810c000c, 'caf8d020', 'TX stream control cached from format before start'),
        ('com.apple.driver.AppleAE2Audio', 0x810c08e8, '0621', 'layout 0/1 TX stream control word index 6'),
    ]
    assert vm_bytes('com.apple.driver.AppleAE2Audio', 0x810c159c, 4) == struct.pack('<I', 0xb0003000)
    assert vm_bytes(amp, 0x80db5004, 4) == struct.pack('<I', 0x80317a9d)
    assert vm_bytes('com.apple.driver.AppleAE2Audio', 0x810c3000, 4) == struct.pack('<I', 0x80317aad)
    assert vm_bytes('com.apple.driver.AppleEmbeddedAudio', 0x80a46018, 4) == struct.pack('<I', 0x80317a9d)
    assert vm_bytes(amp, 0x80db50e8, 4) == struct.pack('<I', 0x80a48208)
    assert vm_bytes('com.apple.driver.AppleEmbeddedAudio', 0x80a48208 + 0x384, 4) == struct.pack('<I', 0x80a3379d)
    anchors += [
        ('stock-kernel', 0x80317aa4, '40420f00', 'IOSleep nanoseconds per millisecond'),
        ('stock-kernel', 0x80317aac, '4ff47a71', 'IODelay scale 1000 nanoseconds'),
        ('stock-kernel', 0x81142a80, '6069216a0268d2f88493326894f825305a4082f00102c847', 'GPIO request XOR polarity XOR 1'),
        ('com.apple.driver.AppleEmbeddedAudio', 0x80a337f8, '0a20', 'reset pulse sleep 10 ms'),
        ('com.apple.driver.AppleEmbeddedAudio', 0x80a33814, '0120', 'reset release sleep 1 ms'),
        ('com.apple.driver.AppleAE2Audio', 0x810c0c0a, '0122', 'revision 4/5 TX stop command'),
    ]
    assert nodes[prefix + 'i2c0/audio-speaker']['function-reset']['cells_after_handle'] == ['0x4750494f', '0x502', '0x10001']
    for bundle, addr, expected, description in anchors:
        assert vm_bytes(bundle, addr, len(bytes.fromhex(expected))) == bytes.fromhex(expected), description
    metadata = json.loads((args.research / 'firmware-kexts/prelink.json').read_text())
    embedded = next(e for e in metadata if e['CFBundleIdentifier'] == 'com.apple.driver.EmbeddedIOP')
    assert embedded['IOKitPersonalities']['AE2']['IOPFirmwareName'] == 'AE2Firmware'
    firmware = loaded['com.apple.driver.IOP_s5l8950xae2_firmware']
    assert len(firmware) == 434176
    print(json.dumps({'tree_sha256': tree['source_sha256'], 'tree_bytes': tree['parsed_bytes'],
                      'checked': ['five AP CDMA FIFO pairs', 'speaker/reference/MCLK providers',
                                  'amp instance vtable', str(len(anchors)) + ' instruction anchors', 'reset GPIO polarity and delay units', 'MCA error acknowledgement mask', 'computed FIFO threshold versus occupancy', 'layout 0/1 stream control', 'amp delay pointer', 'no declared audio power-provider keys', 'AE2 firmware service'],
                      'amp_vtable': table, 'ae2_provider_bytes': len(firmware),
                      'ae2_provider_sha256': hashlib.sha256(firmware).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()

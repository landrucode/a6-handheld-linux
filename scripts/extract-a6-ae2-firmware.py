#!/usr/bin/env python3
"""Extract N42 AE2 firmware from the owner's unpacked 14G61 kernelcache.

Private offline output only; the raw image requires host configuration and
page tables before it can be booted. This script never accesses a device.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
KERNEL_SHA = 'bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
PROVIDER_SHA = '37c5a779d9446e15436e0f839d45e9dad5afb7eb3f859fdbda4fdb00999ca904'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'build'):
        raise ValueError('proprietary outputs must stay in ignored build/')
    with args.kernel.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != KERNEL_SHA:
            raise ValueError('expected owner N42 14G61 unpacked kernelcache')
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    if not (output / "provider").resolve().is_relative_to(ROOT / "build"):
        raise ValueError("provider output escapes private build directory")
    spec = importlib.util.spec_from_file_location('extract', ROOT / 'scripts/extract-a6-stock-touch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.extract(args.kernel, output / 'provider', ['IOP_s5l8950xae2_firmware'])
    for private in (output / 'provider').iterdir():
        if private.is_file():
            private.chmod(0o600)
    provider = output / 'provider/com.apple.driver.IOP_s5l8950xae2_firmware.macho'
    data = provider.read_bytes()
    if hashlib.sha256(data).hexdigest() != PROVIDER_SHA:
        raise ValueError('stock provider hash mismatch')
    sections = []
    for kind, command in module.commands(data):
        if kind != 1:
            continue
        count = struct.unpack_from('<I', command, 48)[0]
        if len(command) != 56 + count * 68:
            raise ValueError('bad section table')
        for index in range(count):
            section = command[56 + index*68:56 + (index+1)*68]
            name = section[:16].split(b'\0')[0]
            address, size, offset = struct.unpack_from('<III', section, 32)
            if name == b'fwFirmwareImage':
                if offset + size > len(data):
                    raise ValueError('firmware outside file')
                sections.append((address, size, offset))
    if sections != [(0x8125e000, 0x66000, 0x2000)]:
        raise ValueError('unexpected N42 firmware section')
    image = data[0x2000:0x68000]
    if struct.unpack_from('<I', image)[0] != 0xea00000e:
        raise ValueError('reset vector mismatch')
    # PC-relative property loads in the pinned provider start routine. These
    # are firmware-buffer offsets, not host physical addresses or MMIO.
    loads = dict(ConfigurationOffset=0xbf6, HeapBaseOffset=0xc0e,
                 HeapSizeOffset=0xc24, HeapRequired=0xc3a,
                 PageTableBase=0xc50, PageTableSize=0xc66,
                 MessageChannelSize=0xc7c, PanicString=0xc92,
                 PanicFunction=0xca8, PanicLog=0xcbe,
                 PanicLogBytes=0xcd4, PanicLogBytesMax=0xcea)
    properties = {}
    for name, pc in loads.items():
        instruction = struct.unpack_from('<H', data, pc)[0]
        if instruction & 0xff00 != 0x4800 or struct.unpack_from('<H', data, pc+2)[0] != 0x4478:
            raise ValueError('property instruction mismatch')
        literal = ((pc+4)&~3) + (instruction&255)*4
        delta = struct.unpack_from('<I', data, literal)[0]
        pointer = pc+6+delta
        if pointer+4 > len(data):
            raise ValueError('property pointer outside provider')
        properties[name] = struct.unpack_from('<I', data, pointer)[0]
    target = output / 'ae2-image.private.bin'
    target.write_bytes(image)
    target.chmod(0o600)
    manifest = dict(kernel_sha256=KERNEL_SHA, provider_sha256=PROVIDER_SHA,
                    image_sha256=hashlib.sha256(image).hexdigest(), image_bytes=len(image),
                    reset_branch_target_offset=0x40, boot_ready=False,
                    properties=properties,
                    pending=['host firmware configuration and page tables',
                             'IPC/channel initialization and DSP route commands',
                             'bounded CPU stop and complete register restore'])
    target = output / 'manifest.private.json'
    target.write_text(json.dumps(manifest, indent=2)+'\n')
    target.chmod(0o600)
    print('Extracted private AE2 image:', len(image), 'bytes; boot_ready=false')


if __name__ == '__main__':
    main()

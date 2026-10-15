#!/usr/bin/env python3
"""Decode stock N42 audio wiring offline. No device access; omit calibration bytes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

spec = importlib.util.spec_from_file_location('platform_tree', Path(__file__).with_name('inspect-a6-platform-tree.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inventory(data):
    nodes = module.parse_tree(data)
    clock_data = nodes['/device-tree/arm-io/pmgr']['device-clocks']
    if len(clock_data) % 44:
        raise ValueError('unexpected PMGR clock record size')
    clocks = {}
    for offset in range(0, len(clock_data), 44):
        record = clock_data[offset:offset + 44]
        identifier = int.from_bytes(record[:4], 'big')
        fields = struct.unpack('<11I', record)
        logical = identifier & 0xff
        if logical in clocks:
            raise ValueError('duplicate logical PMGR clock')
        clocks[logical] = {
            'identifier': hex(identifier), 'name': record[28:].split(b'\0')[0].decode('ascii'),
            'parent': fields[2], 'register_index': fields[3],
            'flags': hex(identifier >> 8),
            # AE2's special clock entry must not be treated as PMGR register zero.
            'pmgr_physical': hex(0x3f101000 + 4 * fields[3]) if not identifier & 0x1000 else None,
        }
    handles = {struct.unpack('>I', p['AAPL,phandle'])[0]: n for n, p in nodes.items() if 'AAPL,phandle' in p}
    selected = {'spi3', 'i2c0', 'audio-codec', 'audio-speaker', 'audio-codec-reference',
                'audio-codec-sidetone', 'audio-codec-voice', 'audio-bluetooth',
                'i2s0', 'i2s1', 'i2s2', 'mca0', 'mca1', 'i2s-switch', 'adsp',
                'ae2', 'vib-pwm', 'vibrator', 'pmu', 'cdma'}
    result = {}
    for path, props in nodes.items():
        if path.rsplit('/', 1)[-1] not in selected:
            continue
        out = {}
        for key, value in props.items():
            if key in {'name', 'compatible', 'device_type'}:
                out[key] = value.rstrip(b'\0').decode('ascii').split('\0')
            elif key in {'speaker-rdc', 'speaker-calib', 'speaker-config', 'speaker-vbca', 'amp_offset'} or 'calibration' in key:
                out[key] = {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
            elif key in {'AAPL,phandle', 'interrupt-parent', 'dma-parent'}:
                handle = struct.unpack('>I', value)[0]
                out[key] = {'handle': hex(handle), 'path': handles.get(handle)}
            elif key.startswith('function-'):
                cells = list(struct.unpack('<' + 'I' * (len(value) // 4), value))
                handle = struct.unpack('>I', value[:4])[0]
                out[key] = {'target': handles.get(handle), 'cells_after_handle': [hex(c) for c in cells[1:]],
                            'selector': cells[1].to_bytes(4, 'big').decode('ascii') if len(cells)>1 else None}
            elif len(value) % 4 == 0:
                cells = list(struct.unpack('<' + 'I' * (len(value) // 4), value))
                out[key] = [hex(c) for c in cells]
                if key == 'reg' and path.count('/') == 3:
                    out['physical_ranges'] = [{'base': hex(0x30000000 + cells[i]), 'size': hex(cells[i+1])} for i in range(0,len(cells),2)]
                if key == 'dma-channels':
                    out['dma_records'] = [{'channel': cells[i], 'fifo_physical': hex(cells[i+1]),
                                           'format': hex(cells[i+2]), 'endpoint': cells[i+3]} for i in range(0,len(cells),4)]
            else:
                out[key] = {'bytes': len(value), 'hex': value.hex()}
        result[path] = out
        if 'clock-gates' in props:
            gates = struct.unpack('<' + 'I' * (len(props['clock-gates']) // 4), props['clock-gates'])
            out['pmgr_clock_records'] = [dict(logical_id=gate, **clocks[gate]) for gate in gates if gate in clocks]
    return {'source_sha256': hashlib.sha256(data).hexdigest(), 'parsed_bytes': len(data), 'nodes': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tree', type=Path)
    args = parser.parse_args()
    data = args.tree.read_bytes()
    if not 8 <= len(data) <= 1048576:
        parser.error('unexpected tree size')
    print(json.dumps(inventory(data), indent=2))


if __name__ == '__main__':
    main()

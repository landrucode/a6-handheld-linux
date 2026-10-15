#!/usr/bin/env python3
"""Decode the fixed read-only A6 handoff snapshot; never changes a RAM map."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def decode(data):
    if len(data) != 0xb00:
        raise ValueError('expected exactly 2816 capture bytes')
    words = struct.unpack('<704I', data)
    if words[0] != 0x41364d31 or words[5] > 36:
        raise ValueError('invalid capture header')
    status = {1:'complete',2:'malformed tree',3:'tree limits exceeded',
              10:'boot argument address rejected (v1 also rejects MMU off)',
              11:'unsupported boot argument version/revision',
              12:'unsupported RAM/tree metadata',13:'tree not readable identity RAM'}
    args = words[8:22]
    report = {'status': words[1], 'status_text': status.get(words[1], 'unknown'),
              'complete_untruncated': words[1] == 1 and words[7] == 0,
              'flags':words[7], 'nodes':words[6],
              'capture_revision':words[25],
              'sctlr':hex(words[22]) if words[25] in (2,3,4,5) else None,
              'last_par':hex(words[23]) if words[25] in (2,3,4,5) else None,
              'last_translation_page':hex(words[24]) if words[25] in (2,3,4,5) else None,
              'boot_args_address':hex(words[2]), 'tree_physical':hex(words[3]),
              'tree_length':words[4], 'revision':args[0]&65535, 'version':args[0]>>16,
              'virt_base':hex(args[1]), 'phys_base':hex(args[2]),
              'reported_ram_bytes':args[3], 'top_of_kernel_data_raw':hex(args[4]),
              'framebuffer_base':hex(args[5]), 'row_bytes':args[7],
              'width':args[8], 'height':args[9], 'depth_raw':args[10],
              'tree_pointer_raw':hex(args[12]), 'records':[]}
    for i in range(words[5]):
        offset = 128 + i*72
        kind, length = struct.unpack_from('<II', data, offset)
        name = data[offset+8:offset+40].split(b'\0',1)[0].decode('ascii', errors='replace')
        value = data[offset+40:offset+72][:min(length,32)]
        record = {'kind': {1:'memory',2:'memory-map'}.get(kind,'unknown'),
                  'name':name,'length':length,'data_hex':value.hex()}
        if name != 'name' and length and length <= 32 and length % 8 == 0:
            record['candidate_address_size_pairs'] = [
                {'address':hex(a),'size':n,'end_exclusive':hex(a+n),
                 'within_reported_ram':args[2] <= a and a+n <= args[2]+args[3]}
                for a,n in struct.iter_unpack('<II',value)]
        report['records'].append(record)
    if words[25] == 3:
        if words[5] > 19:
            raise ValueError('touch capture overlaps memory records')
        calibration = data[0x600:0xa00]
        proximity = data[0xa00:0xa80]
        valid = words[1] == 1 and words[7] == 0 and words[26:30] == (3,1,1024,128)
        actual_counts = (sum(x != 0 for x in calibration), sum(x != 0 for x in proximity))
        report['touch_capture'] = {
            'valid': valid and words[30:32] == actual_counts,
            'flags': words[26], 'matching_nodes': words[27],
            'calibration_bytes': words[28], 'proximity_bytes': words[29],
            'nonzero_bytes': list(actual_counts),
            'calibration_sha256': hashlib.sha256(calibration).hexdigest(),
            'proximity_sha256': hashlib.sha256(proximity).hexdigest(),
            'limitation': 'Read-only n41 data capture, not proof of usable calibration or driver compatibility.'}
    if words[25] in (4,5):
        if words[5] > 19:
            raise ValueError('clock capture overlaps memory records')
        table = data[0x600:0x780]
        nonzero = sum(x != 0 for x in table)
        report['clock_capture'] = {
            'valid': words[1] == 1 and words[7] == 0 and words[26:29] == (1,1,384) and words[29] == nonzero,
            'flags': words[26], 'matching_nodes': words[27],
            'bytes': words[28], 'nonzero_bytes': nonzero,
            'sha256': hashlib.sha256(table).hexdigest(),
            'le32_words': list(struct.unpack('<96I', table)),
            'limitation': 'Raw live clock table; entry layout and clock-ID mapping require separate validation.'}
    if words[25] == 5:
        cpu=words[480:486]
        report['cpu_clock_capture'] = {
            'valid': report['complete_untruncated'] and cpu[0:2]==(3,1) and cpu[2] in (4,8) and cpu[5]==1,
            'flags':cpu[0], 'cpu0_nodes':cpu[1], 'bytes':cpu[2],
            'fixed_frequency_hz':cpu[3]+(cpu[4]<<32), 'cpus_nodes':cpu[5],
            'limitation':'Firmware CPU0 fixed-frequency, not a physical measurement of PWM output.'}
    report['limitation'] = 'Captured firmware evidence only; completeness does not prove all firmware reservations or authorize RAM expansion.'
    return report

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    args=parser.parse_args()
    print(json.dumps(decode(args.capture.read_bytes()),indent=2))

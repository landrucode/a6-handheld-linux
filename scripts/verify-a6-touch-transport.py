#!/usr/bin/env python3
"""Verify linked touch-observer permissions, callback lifetime and DT/config."""
from pathlib import Path
import json
import struct
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
kind = sys.argv[1] if len(sys.argv) > 1 else 'touch-transport'
assert kind in ('touch-transport', 'touch-check', 'touch-check-start', 'touch-clock', 'touch-pwm-check', 'touch-pwm-readback', 'touch-pwm-steady', 'touch-i2c', 'touch-pmu-read', 'touch-power-check', 'touch-gpio-cs', 'touch-hbpp', 'touch-n1-version', 'touch-n1-start-version', 'touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42')
out = repo / ('build/linux-a6-' + kind)
raw = (out / 'arch/arm/boot/Image').read_bytes()
symbols = {}
for line in subprocess.check_output(['llvm-nm', '-S', '-n', str(out / 'vmlinux')], text=True).splitlines():
    fields = line.split()
    if len(fields) == 4:
        symbols[fields[3]] = (int(fields[0], 16), int(fields[1], 16))
    elif len(fields) == 3:
        symbols[fields[2]] = (int(fields[0], 16), 0)


def address(name):
    return symbols[name][0]


def contents(name):
    addr, size = symbols[name]
    offset = addr - 0xc0008000
    assert 0 <= offset and offset + size <= len(raw), name
    return raw[offset:offset + size]


report = {}
attributes = [
    ('a6_touch_status_attr', 0o400, 'a6_touch_status_show', 8),
    ('a6_touch_clock_attr', 0o200, 'a6_touch_enable_clock_store', 12),
]
if kind.startswith('touch-check') or kind in ('touch-pwm-check', 'touch-pwm-readback', 'touch-pwm-steady', 'touch-power-check', 'touch-gpio-cs', 'touch-hbpp', 'touch-n1-version', 'touch-n1-start-version', 'touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [
        ('a6_check_result_attr', 0o400, 'a6_check_result_show', 8),
        ('a6_check_run_attr', 0o200, 'a6_check_run_store', 12),
    ]
if kind in ('touch-clock', 'touch-pwm-check', 'touch-pwm-readback', 'touch-pwm-steady', 'touch-power-check', 'touch-gpio-cs', 'touch-hbpp', 'touch-n1-version', 'touch-n1-start-version', 'touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [
        ('a6_pwm_status_attr', 0o400, 'a6_pwm_status_show', 8),
        ('a6_pwm_enable_attr', 0o200, 'a6_pwm_enable_store', 12),
    ]
if kind in ('touch-i2c', 'touch-pmu-read'):
    assert 'a6_check_run_store' not in symbols
    assert 'a6_pwm_probe_start' not in symbols
if kind in ('touch-i2c', 'touch-pmu-read', 'touch-power-check', 'touch-gpio-cs', 'touch-hbpp', 'touch-n1-version', 'touch-n1-start-version', 'touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [
        ('a6_i2c_status_attr', 0o400, 'a6_i2c_status_show', 8),
        ('a6_i2c_enable_attr', 0o200, 'a6_i2c_enable_store', 12),
    ]
if kind == 'touch-pmu-read':
    attributes += [
        ('a6_pmu_result_attr', 0o400, 'a6_pmu_result_show', 8),
        ('a6_pmu_run_attr', 0o200, 'a6_pmu_run_store', 12),
    ]
if kind in ('touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [
        ('a6_fw_status_attr', 0o400, 'a6_fw_status_show', 8),
        ('a6_fw_run_attr', 0o200, 'a6_fw_run_store', 12),
    ]
if kind in ('touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [
        ('a6_post_status_attr', 0o400, 'a6_post_status_show', 8),
    ]
if kind in ('touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [('a6_report_status_attr', 0o400, 'a6_report_status_show', 8)]
if kind in ('touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42'):
    attributes += [('a6_cal_status_attr', 0o400, 'a6_cal_status_show', 8)]
for attribute, mode, callback, slot in attributes:
    data = contents(attribute)
    assert len(data) == 16, attribute
    assert struct.unpack_from('<H', data, 4)[0] == mode, attribute
    pointer = struct.unpack_from('<I', data, slot)[0]
    assert (pointer & ~1) == (address(callback) & ~1), callback
    assert address('_stext') <= (pointer & ~1) < address('_etext'), callback
    assert struct.unpack_from('<I', data, 20 - slot)[0] == 0, attribute
    report[attribute] = {'mode': oct(mode), 'callback': callback,
                         'address': hex(pointer), 'permanent_text': True}

assert address('__init_begin') <= address('a6_touch_transport_init') < address('__init_end')
assert struct.unpack('<8I', contents('a6_touch_status_show.offsets')) == (0, 4, 8, 12, 48, 52, 56, 76)
current = (repo / ('build/arm/a6-n42ap-' + kind + '.dtb')).read_bytes()
assert current == (repo / 'build/arm/a6-n42ap-arch-direct-drm-ram768.dtb').read_bytes()


def config(path):
    return {line for line in path.read_text().splitlines()
            if line.startswith(('CONFIG_', '# CONFIG_'))}


reference_config = ('build/linux-a6-charger-vbat-hdq-echo-guard/.config'
                    if kind in ('touch-fw-n42', 'touch-post-n42', 'touch-report-n42', 'touch-full-n42', 'touch-retry-n42', 'touch-clk32-n42', 'touch-e3-info-n42') else
                    'build/linux-a6-arch-direct-drm/.config')
assert config(out / '.config') == config(repo / reference_config)
report['dt_byte_identical_to_proven_768m'] = True
report['config_identical_to_reference'] = reference_config
report['spi_read_offsets_exclude_rxdata'] = True
print(json.dumps(report, indent=2))

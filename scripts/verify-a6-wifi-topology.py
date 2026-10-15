#!/usr/bin/env python3
"""Verify pinned N42 Wi-Fi routes offline; never access phone, MAC or calibration."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adt', ROOT / 'scripts/inspect-a6-platform-tree.py')
adt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adt)
WLAN = '/device-tree/arm-io/usb-complex/usb-ehci/wlan'
EHCI = WLAN.rsplit('/',1)[0]
BUS = EHCI.rsplit('/',1)[0]
IO = BUS.rsplit('/',1)[0]
SOURCES = (
    ('.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw', 'a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef'),
    ('build/touch-research/DeviceTree-ios10.raw', '9dfa77a3e1db226a304abb643dc829ed2e7d305beebfdc67d965eb255837736d'),
)
KEYS = ('port','port-type','hsic-port-errata','clock-mask','interrupts','port-timing',
        'function-device_reset','function-device_ready','function-host_ready','function-remote_wake')
prior = None
clock_prior = None
results = []
CLOCK_RECORDS = {
    0x34: ('USB-PHY', 0x604, 0, 0),
    0x36: ('USB-EHCI', 4, 0x23, 0x5a),
    0x37: ('USB-OHCI0', 0x60504, 0x25, 0),
    0x38: ('USB-OHCI1', 0x60504, 0x26, 0),
    0x39: ('USB-PHY0-CLK', 0, 0, 0x53),
    0x3a: ('USB-PHY1-CLK', 0, 0, 0x59),
}
for name, expected in SOURCES:
    raw = (ROOT / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise SystemExit('stock tree hash mismatch: ' + name)
    nodes = adt.parse_tree(raw)
    gates = struct.unpack('<8I', nodes[BUS]['clock-gates'])
    assert gates == (0x35, 0x36, 0x37, 0x38, 0x34, 0x39, 0x3a, 0x3b)
    assert int.from_bytes(nodes[WLAN]['clock-mask'], 'little') == 0x30042
    raw_clocks = nodes[IO + '/pmgr']['device-clocks']
    assert len(raw_clocks) % 44 == 0
    clocks = {}
    for offset in range(0, len(raw_clocks), 44):
        record = raw_clocks[offset:offset+44]
        identifier = int.from_bytes(record[:4], 'big')
        if identifier not in gates:
            continue
        assert identifier not in clocks, 'duplicate USB clock identifier'
        fields = struct.unpack('<11I', record)
        clock_name = record[28:].split(b'\0', 1)[0].decode('ascii')
        clocks[identifier] = (clock_name, fields[2], fields[3], fields[4])
    assert clocks == CLOCK_RECORDS, 'USB clock record layout changed'
    if clock_prior is not None:
        assert clocks == clock_prior, 'USB clock records differ between stock versions'
    clock_prior = clocks
    wlan = {key:nodes[WLAN][key] for key in KEYS}
    if prior is not None and wlan != prior:
        raise SystemExit('Wi-Fi routing/timing differs between stock versions')
    prior = wlan
    io = struct.unpack('<III',nodes[IO]['ranges'])
    bus = struct.unpack('<III',nodes[BUS]['ranges'])
    regs = struct.unpack('<IIII',nodes[EHCI]['reg'])
    assert io == (0,0x30000000,0x10000000)
    assert bus == (0,0x06100000,0x00600000)
    assert regs == (0x00300000,0x10000,0x00600000,0x10000)
    assert bus[0] <= regs[0] and regs[0] + regs[1] <= bus[0] + bus[2]
    parent = bus[1] + regs[0] - bus[0]
    assert io[0] <= parent and parent + regs[1] <= io[0] + io[2]
    physical = io[1] + parent - io[0]
    assert physical == 0x36400000
    assert int.from_bytes(wlan['port'],'little') == 4
    assert int.from_bytes(wlan['port-type'],'little') == 3
    functions = {}
    for key in KEYS:
        if not key.startswith('function-'):continue
        value = wlan[key]
        assert len(value) == 16 and value[4:8] == b'OIPG'
        owners = [p for p,props in nodes.items() if props.get('AAPL,phandle') == value[:4]]
        assert len(owners) == 1
        functions[key] = {'provider':owners[0], 'pin_word':hex(int.from_bytes(value[8:12],'little')), 'flags_raw':value[12:].hex()}
    assert functions['function-device_reset']['provider'] == '/device-tree/arm-io/i2c0/pmu'
    assert nodes['/device-tree/arm-io/i2c0/pmu']['compatible'] == b'pmu,d1972\0'
    assert all(functions[key]['provider'] == '/device-tree/arm-io/gpio' for key in functions if key != 'function-device_reset')
    results.append({'source':name,'sha256':expected,'ehci_first_window_physical':hex(physical),
                    'ehci_second_window_inside_declared_range':regs[2]+regs[3] <= bus[0]+bus[2],
                    'functions':functions})
usb = ROOT / '.deps/linux/drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c'
text = usb.read_text()
mapping = text.split('static const struct brcmf_firmware_mapping brcmf_usb_fwnames[] = {',1)[1].split('};',1)[0]
print(json.dumps({'stock_routes_match':True,'sources':results,
                  'usb_clock_records_match':True,
                  'usb_clock_records':{hex(key):value for key,value in CLOCK_RECORDS.items()},
                  'usb_clock_dispatch_verified':False,
                  'usb_driver_sha256':hashlib.sha256(usb.read_bytes()).hexdigest(),
                  'usb_firmware_mapping_has_4334':'BRCM_CC_4334_CHIP_ID' in mapping,
                  'hardware_tested':False},indent=2))

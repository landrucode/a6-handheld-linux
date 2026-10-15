#!/usr/bin/env python3
"""Read-only validation of pinned stock N1 CHECK dispatch and GPIO descriptors."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess

repo = Path(__file__).resolve().parents[1]
path = repo / 'build/touch-research/AppleMultitouchSPI-ios10.macho'
data = path.read_bytes()
assert hashlib.sha256(data).hexdigest() == 'bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0'
base = 0x80854000

def word(address):
    return struct.unpack_from('<I', data, address-base)[0]

def expect(address, encoded):
    expected = bytes.fromhex(encoded)
    assert data[address-base:address-base+len(expected)] == expected, hex(address)

# Constructor loads literal, adds PC, skips two ABI header words, stores vptr.
expect(0x80861470, '0249794408310160')
vtable = 0x80861472 + 4 + word(0x8086147c) + 8
assert vtable == 0x808684d4
assert word(vtable + 0x34c) == 0x80855e65
# Four stack bytes 05 00 00 06, four-byte TX/RX setup, reply-byte compare d0.
expect(0x80855e72, '05208df8140000258df815508df8165006208df81700')
expect(0x80855ea6, '042500950df1140a0df1100b042251465b46b047')
expect(0x80855eec, '9df81000d028')


spi = (repo / 'build/touch-research/AppleSamsungSPI-ios10.macho').read_bytes()
assert hashlib.sha256(spi).hexdigest() == 'ef0da50af5d1343e5cfc1d8a69192964d85db8593dd625abba0226153e943a9f'
for address, encoded in {
    0x807df890: '0d20c4f8e000',  # cached CONTROL=RUN|TXRESET|RXRESET
    0x807e0b94: 'd4f8e020d0f8cc3300212046',  # write cached CONTROL
    0x807e059c: '2068d0f8841320468847',  # configure/start before PIO/TX
    0x807e05f4: '41f02002042120469847',  # enable PIO
    0x807e0620: '0a78102120469847',  # write TX byte
}.items():
    expected_bytes = bytes.fromhex(encoded)
    offset = address - 0x807de000
    assert spi[offset:offset+len(expected_bytes)] == expected_bytes, hex(address)

tree = repo / '.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw'
assert hashlib.sha256(tree.read_bytes()).hexdigest() == 'a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef'
inventory = json.loads(subprocess.check_output([
    'python3', str(repo / 'scripts/inspect-a6-touch-tree.py'), str(tree)]))
nodes = [n for n in inventory['nodes'] if n['path'] == '/device-tree/arm-io/spi1/multi-touch']
assert len(nodes) == 1
props = nodes[0]['properties']
expected = {
    'function-enable_cs': '0000000f4f4950470106000001010000',
    'function-reset': '0000000f4f495047071c000001000100',
}
for key, value in expected.items():
    assert props[key]['hex'] == value, key
assert 'function-enable_download' not in props
print(json.dumps({
    'n1_vtable': hex(vtable), 'check_handler': hex(word(vtable+0x34c)),
    'stock_spi_run_before_fifo_verified': True,
    'command': '05000006', 'response_first_byte': 'd0',
    'touch_gpio_descriptors': expected, 'dedicated_download_gpio': False,
    'limitation': 'Static stock-code proof only, not a powered-controller or hardware response test.'
}, indent=2))

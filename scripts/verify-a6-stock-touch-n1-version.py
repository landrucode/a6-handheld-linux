#!/usr/bin/env python3
"""Pin the stock N1 controller-version read used before calibration."""
from pathlib import Path
import hashlib, json, struct
repo = Path(__file__).resolve().parents[1]
p = repo/'build/touch-research/AppleMultitouchSPI-ios10.macho'
b = p.read_bytes()
assert hashlib.sha256(b).hexdigest() == 'bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0'
def raw(a,n): return b[a-0x80854000:a-0x80854000+n]
def word(a): return struct.unpack('<I',raw(a,4))[0]
def expect(a,h): assert raw(a,len(bytes.fromhex(h))) == bytes.fromhex(h),hex(a)
# N1 driver's slot534 calls the eight-byte controller-version helper.
v = 0x808684d4
assert word(v+0x534) == 0x8085dfe9
expect(0x8085dfe8,'f0b503af2de9000d')
# Address 0x10008ffc is encoded as 1c 73 + BE address bytes + BE sum 019b.
expect(0x8085e006,'1c208df81c0073208df81d004fea16210df11c0808f102008df81e108df81f604fea16618df820104fea16418df82110042102f0d6ff010a8df822108df82300')
# The wrapper requests eight TX and eight RX bytes through slot35c.
expect(0x8085df62,'686d0168d1f85c63cde90144082400940df1180a')
# Stock packs RX bytes2..5 little-endian and compares to 0x434d11a0.
expect(0x8085dfb0,'43ea022241ea002040ea0240c8f80000')
expect(0x80862608,'a0114d43')
# The N1 calibration caller invokes slot534 before later controller writes.
expect(0x80862480,'2068d0f834255e49204690478046a868')
print(json.dumps({
 'driver_vtable':hex(v), 'version_reader':hex(word(v+0x534)),
 'request':'1c738ffc1000019b', 'tx_bytes':8, 'rx_bytes':8,
 'packed_expected_version':'0x434d11a0',
 'limitation':'Static protocol proof; this diagnostic performs only the version read.'
}, indent=2))

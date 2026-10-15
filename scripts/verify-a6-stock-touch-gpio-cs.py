#!/usr/bin/env python3
"""Pinned n42 external chip-select dispatch/polarity; no hardware access."""
from pathlib import Path
import hashlib,struct,json,subprocess
repo=Path(__file__).resolve().parents[1]
def load(path,base,digest):
 b=(repo/path).read_bytes();assert hashlib.sha256(b).hexdigest()==digest
 return lambda a,n:b[a-base:a-base+n]
def word(r,a):return struct.unpack('<I',r(a,4))[0]
def expect(r,a,h):assert r(a,len(bytes.fromhex(h)))==bytes.fromhex(h),hex(a)
spi=load('build/touch-research/AppleSamsungSPI-ios10.macho',0x807de000,'ef0da50af5d1343e5cfc1d8a69192964d85db8593dd625abba0226153e943a9f')
gpio=load('build/touch-research/ios10-touch-dependencies/com.apple.driver.AppleS5L8930X.macho',0x81141000,'08016671a8a5ad527c1e6c1485163d400ae9c75f9a728d370e1f629ced42a30b')
assert 0x807df3de+word(spi,0x807df3e4)+8==0x807e30cc
assert word(spi,0x807e30cc+0x3b0)==0x807e1459
assert word(spi,0x807e30cc+0x3b4)==0x807e14bd
assert spi(0x807df63c+word(spi,0x807df828),12)==b'internal-cs\0'
assert spi(0x807dfa34+word(spi,0x807dfabc),18)==b'function-spi_cs%d\0'
assert 0x8114209a+word(gpio,0x811420a0)+8==0x81146920
assert word(gpio,0x81146920+0x384)==0x811428f5
assert word(gpio,0x81146920+0x380)==0x8114282d
assert 0x8114298a+word(gpio,0x81142990)+8==0x81146d04
assert word(gpio,0x81146d04+0x3c)==0x81142a5d
expect(spi,0x807df644,'002818bf012084f8b000')
expect(spi,0x807dfada,'dbf8001001f0030105eb8101d1f89010c5f8fc10')
expect(spi,0x807e1476,'95f8b00030b12868d0f8b42328462146904709e00094d5f8fc000168d1f83c90694600220023c847')
expect(spi,0x807e05d8,'2068d0f8b023012120469047')
expect(spi,0x807e0934,'2068d0f8b023002120469047')
expect(gpio,0x81142b22,'04f11805e0680168896e884760f98f0a45f98f0a')
expect(gpio,0x81142a80,'6069216a0268d2f88493326894f825305a4082f00102c847')
expect(gpio,0x811428f4,'0368d3f880c30e23002a18bf0f231a466047')
expect(gpio,0x811428a0,'4ff0010b6f224bf00200114603e0')
assert gpio(0x81142860+14,2)==bytes([0x22,0x20]) # mode14->a4, mode15->a0
j=json.loads(subprocess.check_output(['python3',str(repo/'scripts/inspect-a6-touch-tree.py'),str(repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw')]))
n={n['path']:n['properties'] for n in j['nodes']}
p=n['/device-tree/arm-io/spi1'];t=n['/device-tree/arm-io/spi1/multi-touch']
assert 'internal-cs' not in p
assert p['function-spi_cs0']['hex']=='0000000f4f4950470106000001000100'
assert t['function-enable_cs']['hex']=='0000000f4f4950470106000001010000'
assert t['reg']['le32'][0]==0
# Descriptor copied at+18 puts polarity byte13 atobject25.
assert (1^0^1)==0 and (0^0^1)==1
assert (0x203&~0x6f)|2==0x202 and (0x202&~0x6f)|3==0x203
print(json.dumps({'external_cs':True,'gpio':49,'asserted':'202','deasserted':'203','internal_pin_register_preserved':'3','limitation':'Static dispatch/polarity proof; hardware response remains untested.'},indent=2))

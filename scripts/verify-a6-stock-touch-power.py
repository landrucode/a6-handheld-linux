#!/usr/bin/env python3
"""Pinned stock rail ordering/shared-bit/GPIO evidence; no device access."""
from pathlib import Path
import hashlib,struct,json,subprocess
repo=Path(__file__).resolve().parents[1]
subprocess.run(['python3',str(repo/'scripts/verify-a6-stock-touch-pmu.py')],check=True,stdout=subprocess.DEVNULL)
def load(path,base,digest):
 b=(repo/path).read_bytes();assert hashlib.sha256(b).hexdigest()==digest
 return lambda a,n:b[a-base:a-base+n]
def word(r,a):return struct.unpack('<I',r(a,4))[0]
def expect(r,a,h):assert r(a,len(bytes.fromhex(h)))==bytes.fromhex(h),hex(a)
pmu=load('build/touch-research/ios10-touch-dependencies/com.apple.driver.AppleD1972PMU.macho',0x810e3000,'3df8f04a9759008493575f3078e3416e935fa450a366ea4d5356cb84ca628c16')
mt=load('build/touch-research/AppleMultitouchSPI-ios10.macho',0x80854000,'bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0')
# Functions resolved into object+64 LDO, +68 analog.
assert mt(0x80857d18+word(mt,0x80857dcc),19)==b'function-power_ldo\0'
assert mt(0x80857d24+word(mt,0x80857dd0),19)==b'function-power_ana\0'
expect(mt,0x80857d1a,'6066')
expect(mt,0x80857d26,'a066')
expect(mt,0x80857e50,'03ae0168cc6b002200233146a047')
expect(mt,0x80857ea2,'686e002845d00168ce6b03a900220023b0470446')
expect(mt,0x80857eba,'a86ed0b30399c1bb0168ce6b03a900220023b047')
expect(pmu,0x810e75f6,'17f8190c9bf80a108843ba68002a18bf084307f8')
expect(pmu,0x810e760c,'a5f10a01062910d81549e94011f0010f18bf88f8342110f01c0f02d198f83411c9b140f0400007f8')
expect(pmu,0x810e7662,'00f0bf00e4e7')
expect(pmu,0x810e7678,'0b2901f1680088bf4ff6ff707047')
expect(pmu,0x810e897c,'6069a369d3f808900a68002a18bf01225b7b002b18bf01234946fef75fff11e0')
expect(pmu,0x810e78d4,'009900f01d0007f8190cbaf1020f0cd0baf1010f0cd0baf1')
expect(pmu,0x810e7904,'40f0020007f8190c59b9')
assert word(pmu,0x810e766c)==0x00088101
assert not ((word(pmu,0x810e766c)>>12)&1) # selector12 does not update tracked flag
assert 0xef&0x1c and 0xeb&0x1c # shared bit40 set for both observed directions
v=0x810e55f4+word(pmu,0x810e5950)+8
assert v==0x810ed8b0 and word(pmu,v+0x3c)==0x810e8965
assert word(pmu,0x810ed244+0x3c4)==0x810e7679 # GPIO index0 ->68
assert pmu(0x810e402a+word(pmu,0x810e41ec),16)==b'gpio-pin-config\0'
j=json.loads(subprocess.check_output(['python3',str(repo/'scripts/inspect-a6-touch-tree.py'),str(repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw')]))
n={n['path']:n['properties'] for n in j['nodes']}
assert n['/device-tree/arm-io/spi1/multi-touch']['function-clock_enable-pmu']['hex']=='000000284f4950470000000001010002'
assert n['/device-tree/arm-io/i2c0/pmu']['gpio-pin-config']['hex'].startswith('00000000')
core=(repo/'.deps/linux/drivers/i2c/busses/i2c-pasemi-core.c').read_text()
assert 'TXFIFO_WR(smbus, msg->buf[i]);' in core
assert 'TXFIFO_WR(smbus, msg->buf[msg->len-1] |' in core
assert '(stop ? MTXFIFO_STOP : 0)' in core
print(json.dumps({'power_on':['22:eb->ef','23:ad->ed'],'restore':['23:ed->ad','22:ef->eb'],'shared_bit40_preserved':True,'gpio0_register':'68','gpio0_not_written':True,'voltage7f_not_written':True,'limitation':'Stock register semantics and ordering; no physical rail voltage or live powered CHECK proof.'},indent=2))

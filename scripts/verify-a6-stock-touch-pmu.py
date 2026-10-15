#!/usr/bin/env python3
"""Check static D1972 PMU evidence; no phone or bus access."""
from pathlib import Path
import hashlib,json,struct,subprocess
repo=Path(__file__).resolve().parents[1]
def load(name,base,digest):
 b=(repo/'build/touch-research/ios10-touch-dependencies'/('com.apple.driver.'+name+'.macho')).read_bytes()
 assert hashlib.sha256(b).hexdigest()==digest,name
 def raw(addr,n):
  offset=addr-base;assert 0<=offset<=len(b)-n
  return b[offset:offset+n]
 return raw
pmu=load('AppleD1972PMU',0x810e3000,'3df8f04a9759008493575f3078e3416e935fa450a366ea4d5356cb84ca628c16')
dialog=load('AppleDialogPMU',0x810de000,'4ecff7959ec77a73bc047bd5f7fafe08eabe0b16bd24dee33965e927f19d0334')
def word(raw,a):return struct.unpack('<I',raw(a,4))[0]
def expect(raw,a,h):
 b=bytes.fromhex(h);assert raw(a,len(b))==b,hex(a)
expect(pmu,0x810e3b7c,'0249794408310160')
vptr=0x810e3b82+word(pmu,0x810e3b88)+8
assert vptr==0x810ed244
assert word(pmu,vptr+0x378)==0x810deb51
assert word(pmu,vptr+0x37c)==0x810de9ed
assert word(pmu,vptr+0x3a4)==0x810e4ce9
expect(pmu,0x810e4ce8,'014878447047')
geometry=0x810e4cee+word(pmu,0x810e4cf0)
assert geometry==0x810ee8f8 and pmu(geometry,10)==bytes.fromhex('01025e1e010000000101')
# Buffer provider dispatch; read mode1 and write mode2, same slot350.
expect(dialog,0x810debd0,'d6f884000168d1f85053')
expect(dialog,0x810debe4,'4ff00101a847')
expect(dialog,0x810dea6c,'d6f884000168d1f85053')
expect(dialog,0x810dea80,'4ff00201a847')
# Bank helper takes high address byte, checks bank count and emits selector+3.
expect(dialog,0x810deaf8,'0b0a07f8053c94f89000b0eb112f')
expect(dialog,0x810deb1a,'4a78')
expect(dialog,0x810deb2c,'cb1c791f01910121009102210122c847')
expect(dialog,0x810deb3c,'20b917f8050c84f89000')
assert pmu(0x810ece34+12*12,12).hex()=='881332141f007f0022000400'
assert pmu(0x810ece34+19*12,12).hex()=='000000000000000023004000'
j=json.loads(subprocess.check_output(['python3',str(repo/'scripts/inspect-a6-touch-tree.py'),str(repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw')]))
assert j['source_sha256']=='a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef'
p=next(n['properties'] for n in j['nodes'] if n['path']=='/device-tree/arm-io/spi1/multi-touch')
assert p['function-power_ana']['hex']=='000000284c756d700c020000'
assert p['function-power_ldo']['hex']=='000000284c756d7013020000'
# Trace raw DT reg into the device descriptor and the controller's one shift.
arm_path=repo/'build/touch-research/ios10-clock-dependencies/com.apple.driver.AppleARMPlatform.macho'
b=arm_path.read_bytes();assert hashlib.sha256(b).hexdigest()=='8087110ae6ce1491538e1dc7d4e4983e01f8cc673f66fb4732a62da7e52d13a5'
arm=lambda a,n:b[a-0x80594000:a-0x80594000+n]
v=0x8059795a+word(arm,0x80597960)+8
assert v==0x805c772c
assert word(arm,v+0x348)==0x80597a81
assert word(arm,v+0x350)==0x80597b9d
assert word(arm,v+0x354)==0x80597ae9
assert arm(0x80597c2c+word(arm,0x80597c84),4)==b'reg\0'
expect(arm,0x80597c46,'10280ad3') # descriptor minimum16 bytes
expect(arm,0x80597aa8,'05f154014ff01002') # copy16 raw bytes into+54
expect(arm,0x8059739c,'d0f8482304f1540128469047') # select device+54
ic=load('AppleS5L8940XI2C',0x80cba000,'a60844d083abc56d5b00af687e6acb2ca24759d9a0c548b6fbb0d1486d501b82')
v=0x80cba856+word(ic,0x80cba85c)+8
assert v==0x80cbc0a0 and word(ic,v+0x348)==0x80cbad1d
assert word(ic,v+0x350)==0x8059738d
expect(ic,0x80cbad1c,'0a685200c0f8d820') # address<<1, exactly once
expect(ic,0x80cbae32,'297911f0040f08bf46f40076') # STOP after pointer in mode1
expect(ic,0x80cbae52,'d4f88c00d4f8d81001f0fe0140f2011211430160')
expect(ic,0x80cbae66,'d4f8e410062262f31f210160') # read count|600
expect(ic,0x80cbb5f8,'d4f88c20516811f4807ffbd1') # RXFIFO empty bit8
# Common prefix rule: bank1 plus reg+length <5e skips bank switching.
expect(dialog,0x810deb08,'012805d15018e16f8a78904201d216e0')
core=(repo/'.deps/linux/drivers/i2c/busses/i2c-pasemi-core.c').read_bytes()
assert hashlib.sha256(core).hexdigest()=='79fba3545729becc1c42f9706f01e5fd782dc06b152a219739d07ca5eeb98181'
print(json.dumps({'pmu_vptr':hex(vptr),'read':'0x810deb50','write':'0x810de9ec','geometry':hex(geometry),'address_bytes':1,'banks':2,'bank_selector':'0x1e','touch_enable_fields':{'ana':{'register':'0x22','mask':'0x04','shared_logic_required':True},'ldo':{'register':'0x23','mask':'0x40'}},'limitation':'Static evidence only. No transport implementation, safe live banking, rail identity or restore proof.'},indent=2))

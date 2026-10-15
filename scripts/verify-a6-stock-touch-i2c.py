#!/usr/bin/env python3
"""Pin n42 I2C0 mapping and the stock register reads used by its observer."""
from pathlib import Path
import hashlib,json,struct,subprocess
repo=Path(__file__).resolve().parents[1]
def checked(path,digest):
 b=(repo/path).read_bytes();assert hashlib.sha256(b).hexdigest()==digest,path
 return b
b=checked('build/touch-research/ios10-touch-dependencies/com.apple.driver.AppleS5L8940XI2C.macho','a60844d083abc56d5b00af687e6acb2ca24759d9a0c548b6fbb0d1486d501b82')
def expect(addr,h):
 x=bytes.fromhex(h);assert b[addr-0x80cba000:addr-0x80cba000+len(x)]==x,hex(addr)
# The same mapped base+8c is used for repeated status, divider and version reads.
expect(0x80cbaf7e,'d4f88c004069')
expect(0x80cbafdc,'d4f88c004069')
expect(0x80cbad6a,'d0f88c00c269')
expect(0x80cbac1a,'896ac0f8a410')
# Native byte-offset accessors, not register indices.
expect(0x80cbad80,'d0f88c0040587047')
expect(0x80cbad88,'d0f88c0042507047')
t=checked('.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw','a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef')
record=bytes.fromhex('0000022900000000000000004600000000000000000000000000000049324330000000000000000000000000')
assert t.count(record)==1
j=json.loads(subprocess.check_output(['python3',str(repo/'scripts/inspect-a6-touch-tree.py'),str(repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw')]))
n={x['path']:x['properties'] for x in j['nodes']}
p=n['/device-tree/arm-io/i2c0'];pmu=n['/device-tree/arm-io/i2c0/pmu']
assert n['/device-tree/arm-io']['ranges']['le32']==[0,0x30000000,0x10000000]
assert p['reg']['le32']==[0x03200000,0x1000] and p['clock-gates']['le32']==[0x29]
assert p['function-iic_sda']['hex']=='0000000f4f4950470207000002010100'
assert p['function-iic_scl']['hex']=='0000000f4f4950470307000002010100'
assert pmu['reg']['le32']==[0x74,2500,0,0] and pmu['compatible']=='pmu,d1972'
s=(repo/'kernel/platform/a6-touch-i2c.inc').read_text()
assert '#define A6_TOUCH_I2C_BASE 0x33200000' in s
assert '#define A6_TOUCH_I2C_GATE 0x118' in s
import re
assert sorted(int(x,16) for x in re.findall(r'readl\(a6_touch_i2c \+ (0x[0-9a-f]+)\)',s))==[0x14,0x1c,0x28]
assert 'writel(gate | 0xf, a6_touch_pmgr + A6_TOUCH_I2C_GATE)' in s
assert len(re.findall(r'\bwritel\(',s))==1
print(json.dumps({'i2c0_base':'0x33200000','gate_index':'0x46','gate_offset':'0x118','sda_gpio':58,'scl_gpio':59,'read_offsets':['0x14','0x1c','0x28'],'pmu_dt_address':'0x74','limitation':'No bus transaction or PMU access; address interpretation still requires provider trace.'},indent=2))

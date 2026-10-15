#!/usr/bin/env python3
"""Emulate a candidate CS42L65 receiver profile from the owner's stock update.

Offline only. The VSP endpoint is explicitly chosen as MCA0/reference,
48 kHz / 16-bit playback, receiver control0x138 enabled, XSP/ADC inactive.
This tests stock behavior under those choices, not a captured iOS route.
The generated register trace stays in ignored build/, never committed.
"""
import os,struct,json
from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
os.umask(0o077)
assert Path.cwd()==Path(__file__).resolve().parents[1], 'run from repository root'
import importlib.util,subprocess
subprocess.run(['python3','scripts/verify-a6-stock-audio.py'],check=True,stdout=subprocess.DEVNULL)
spec=importlib.util.spec_from_file_location('dt','scripts/inspect-a6-platform-tree.py');dt=importlib.util.module_from_spec(spec);spec.loader.exec_module(dt)
tree=dt.parse_tree(Path('build/touch-research/DeviceTree-ios10.raw').read_bytes())
reference_only=os.environ.get('A6_CODEC_REFERENCE_ONLY')=='1'
endpoint_format=bytearray(tree['/device-tree/arm-io/mca0/audio-codec-reference']['reg'])
endpoint_format[16:20]=struct.pack('<HH',48,1);endpoint_format[30:32]=bytes([16,16]);endpoint_format=bytes(endpoint_format)
codec_bytes=Path('build/audio-research/ios10/com.apple.driver.AppleCS42L65Audio.macho').read_bytes()
# Static initializer81042828..40 interns VSP first, XSP second.
for pool,pc,expected in [(0x81042c10,0x8104282c,b'vsp\0'),(0x81042c18,0x8104283a,b'xsp\0')]:
 address=pc+struct.unpack_from('<i',codec_bytes,pool-0x8103e000)[0]
 assert codec_bytes[address-0x8103e000:address-0x8103e000+4]==expected
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
for base,size,path in [(0x8103e000,0x10000,'ios10/com.apple.driver.AppleCS42L65Audio.macho'),(0x80a32000,0x30000,'ios10/com.apple.driver.AppleEmbeddedAudio.macho')]:
 u.mem_map(base,size);u.mem_write(base,Path('build/audio-research/'+path).read_bytes())
u.mem_map(0x100000,0x100000);u.mem_map(0x80300000,0x100000)
def w(a,v):u.mem_write(a,struct.pack('<I',v))
def r(a):return struct.unpack('<I',u.mem_read(a,4))[0]
obj=0x100000;w(0x81045348,0x121000);w(0x8104534c,0x121010);w(obj,0x8104413c);w(0x112000,0x113000);w(0x113390,0x114001);w(0x113344,0x114021);w(obj+0x134,0x115000);w(0x115000,0x116000);w(0x1160a0,0x117001);w(obj+0x138,0x115000);w(0x1164f4,0x117001);u.mem_write(obj+0xd1,b"\x01");regs={5:0xb1,6:0x25,7:4,14:0,15:0,16:0xc0,18:0,19:0xd0,46:0xd0,0x218:0,0x242:0x2b,0x243:0,0x24f:0xe0,0xc804:0x45};events=[];phase='init';receiver_enabled=False
def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
def missing(uc,access,address,size,value,data):
 if access==UC_MEM_READ_UNMAPPED and address>=0x80000000:uc.mem_map(address&~4095,4096);return True
 return False
u.hook_add(UC_HOOK_MEM_READ_UNMAPPED,missing)
def hook(uc,a,size,data):
 q=[uc.reg_read(k) for k in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
 if a==0x81043b24:ret(0x112000);return
 if a==0x117000:ret();return
 if a==0x114000:ret(16);return
 if a==0x114020:u.mem_write(q[1],endpoint_format);ret();return
 if a==0x80306140:ret(0x110000);return
 if a in [0x80a39658,0x80a3973c,0x80a39a4c]:
  if a==0x80a3973c:events.append([phase,'read',q[1],regs.get(q[1],0)]);ret(regs.get(q[1],0));return
  if a==0x80a39a4c:val=(regs.get(q[1],0)&~q[2])|q[3];events.append([phase,'mask',q[1],q[2],q[3],val])
  else:val=q[2];events.append([phase,'write',q[1],val])
  regs[q[1]]=val;ret(0);return
 if a==0x80a35d50:ret(12000000);return
 if a==0x80a35d90:events.append([phase,'clock_enable',q[1]]);ret(1);return
 if a==0x80a3377c:events.append([phase,'generic_reset',q[1]]);ret(0);return
 if a==0x810438a4:events.append([phase,'sleep',q[0]]);ret();return
 # The codec's auxiliary Mikey object lifecycle, not codec register I/O.
 if a==0x80a35158:uc.reg_write(UC_ARM_REG_R1,48000);ret(0);return
 if a==0x80a351d4:ret(1 if q[1]==2 else 0);return
 if a==0x80a34e38:events.append([phase,'channel_control',q[1],q[2],q[3]]);ret(q[3]);return
 if a==0x80a34e14:events.append([phase,'control',q[1],q[2]]);ret(0 if receiver_enabled and q[1]==0x138 else q[2]);return
 if a==0x81043994:
  assert (q[1],u.reg_read(UC_ARM_REG_LR)) in [(0x121000,0x8103f435),(0x121010,0x8103f455)]
  events.append([phase,'port_count','vsp' if q[1]==0x121000 else 'xsp']);ret(int(q[1]==(0x121010 if reference_only else 0x121000)));return
 if a==0x81043984:events.append([phase,'channel_role',hex(q[1]),q[3]]);ret(0x766f6963 if q[3]==0 else 0);return
 if a==0x81043974:assert q[1]==(0x121010 if reference_only else 0x121000);events.append([phase,'vsp_direction_flags',2]);ret(2);return
 if a==0x80a39824:events.append([phase,'block_read',q[1],q[3]]);u.mem_write(q[2],bytes(regs.get(q[1]+i,0) for i in range(q[3])));ret();return
 if a==0x80a39938:data=bytes(u.mem_read(q[2],q[3]));events.append([phase,'block_write',q[1],data.hex()]);regs.update({q[1]+i:v for i,v in enumerate(data)});ret();return
 if a==0x81043bf4:ret(int(bytes(u.mem_read(q[0],q[2]))!=bytes(u.mem_read(q[1],q[2]))));return
 if a==0x810439a4:ret();return
 if a==0x810439d4:events.append([phase,'mikey_state',q[1]]);ret();return
 if a>=0x81043890:raise RuntimeError('unmodeled imported service '+hex(a)+' args '+str(q))
u.hook_add(UC_HOOK_CODE,hook)
for addr,phase,arg in [(0x8103f208,'muted_init',1),(0x8103f404,'receiver_enable',0),(0x8103f404,'receiver_mute',0)]:
 receiver_enabled=phase=='receiver_enable' and not reference_only
 for k,v in [(UC_ARM_REG_R0,obj),(UC_ARM_REG_R1,arg),(UC_ARM_REG_SP,0x1f0000),(UC_ARM_REG_LR,0x1e0001)]:u.reg_write(k,v)
 try:u.emu_start(addr|1,0x1e0000,count=100000)
 except Exception:
  print('PC',hex(u.reg_read(UC_ARM_REG_PC)));print(json.dumps(events[-8:],indent=2));raise
 assert u.reg_read(UC_ARM_REG_PC)==0x1e0000
assert regs[5]==0xb1
assert not any(e[1]=='write' and e[2] in (0xc81a,0xc81b) for e in events), 'A0-only patch on B1'
assert (regs[0x13],regs[0x2e])==((0xc0,0x80) if reference_only else (0x80,0xc0)), 'VSP RX active, TX and XSP inactive'
assert reference_only or [regs[x] for x in range(0x16,0x1e)]==[0x80,0x82,4,0x86,0x88,0x8a,0x8c,0x8e], 'only VSP RX slot2 active'
assert regs[0x24f]==0xe0
assert reference_only or (regs[0x251]==1 and regs[0x301]==0x4c)
assert reference_only or any(e[0:4]==['receiver_enable','mask',0x24f,0xa0] and e[4]==0x80 for e in events)
assert reference_only or regs[0x252]==regs[0x253]==0x19
assert not regs[0x2e]&0x10 and regs[0x2f]==0, 'stock XSP clock-role initialization'
assert int.from_bytes(tree['/device-tree/arm-io/spi3/audio-codec']['function-xsp_master'][:4],'big')==int.from_bytes(tree['/device-tree/arm-io/mca0/audio-codec-reference']['AAPL,phandle'],'big')
assert not any(e[1]=='channel_control' and e[2]==0x171 for e in events), 'unrequested analog input'
print('PASS: stock B1 codec profile, VSP/XSP identity, MCA0 reference packing, receiver enable; offline candidate choices only')
Path('build/audio-research/'+('codec-b1-mca-xsp-reference.private.json' if reference_only else 'codec-b1-mca-vsp.private.json')).write_text(json.dumps({'profile':'Explicit candidate: MCA0 reference descriptor, VSP playback only, receiver unmuted, XSP and ADC inactive; not a captured iOS stream','events':events},indent=2)+'\n')

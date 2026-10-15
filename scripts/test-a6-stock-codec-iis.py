#!/usr/bin/env python3
"""Run stock IIS version3 format code for the N42 codec; offline only."""
import subprocess
subprocess.run(["python3","scripts/verify-a6-stock-audio.py"],check=True,stdout=subprocess.DEVNULL)
import struct,importlib.util
from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
spec=importlib.util.spec_from_file_location('dt','scripts/inspect-a6-platform-tree.py');dt=importlib.util.module_from_spec(spec);spec.loader.exec_module(dt)
props=dt.parse_tree(Path('build/touch-research/DeviceTree-ios10.raw').read_bytes())
fmt=bytearray(props['/device-tree/arm-io/i2s0/audio-codec']['reg']);fmt[30:32]=bytes([16,16]);fmt[16:20]=struct.pack('<HH',48,1)
original_fmt=bytes(fmt)
for descriptor_master in (True,False):
 fmt=bytearray(original_fmt)
 if not descriptor_master:fmt[0]&=~1
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
 for base,size,path in [(0x811a4000,0x10000,'ios10/com.apple.driver.AppleSamsungI2S-analysis.macho'),(0x80594000,0x40000,'dma-platform-followup/com.apple.driver.AppleARMPlatform.macho')]:
  u.mem_map(base,size);u.mem_write(base,Path('build/audio-research/'+path).read_bytes()[:size])
 u.mem_map(0x100000,0x100000)
 def w(a,v):u.mem_write(a,struct.pack('<I',v))
 def r(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 obj=0x100000;w(obj+0x90,3);w(obj+0x84,0x102000);w(0x102000,0x103000);w(0x10334c,0x104001);w(obj+0x8c,0x105000);w(obj+0xc4,0x106000);u.mem_write(0x101000,bytes(fmt))
 route=[]
 def hook(uc,a,size,x):
  if a==0x811a5d3c:
   route.append((uc.reg_read(UC_ARM_REG_R1),uc.reg_read(UC_ARM_REG_R2)));ret(0);return
  if a==0x104000:uc.reg_write(UC_ARM_REG_R1,0);ret(24000000)
 u.hook_add(UC_HOOK_CODE,hook)
 def missing(uc,access,address,size,value,x):print('unmapped',hex(address),'PC',hex(uc.reg_read(UC_ARM_REG_PC)));return False
 u.hook_add(UC_HOOK_MEM_INVALID,missing)
 for k,v in [(UC_ARM_REG_R0,obj),(UC_ARM_REG_R1,0),(UC_ARM_REG_R2,0x101000),(UC_ARM_REG_SP,0x1f0000),(UC_ARM_REG_LR,0x1e0001)]:u.reg_write(k,v)
 u.emu_start(0x811a4f4d,0x1e0000,count=100000)
 assert u.reg_read(UC_ARM_REG_PC)==0x1e0000
 assert r(0x105004)==(0x03000099 if descriptor_master else 0x03100099)
 assert r(0x105030)==0x1000 and r(0x10503c)==1
 assert r(0x105040)==(500 if descriptor_master else 0)
 assert r(obj+0xc8)==(0 if descriptor_master else 1)
 assert route==[(3,2 if descriptor_master else 1)]
 assert r(obj+0xa8)==r(obj+0xac)==0x01feca06
 assert r(obj+0xb4)==1536000
print('PASS: stock IIS0 stereo16 format and both clock roles: DT master flag -> mode03000099/divider500/route2; cleared flag -> mode03100099/divider0/route1')

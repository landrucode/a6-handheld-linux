#!/usr/bin/env python3
"""Emulate stock CS42L65 SPI framing against the owner's pinned update.

No phone access. Stock bytes and register sequences remain under build/.
"""
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
# Existing verification pins source hashes and the inherited audio transport.
import subprocess
subprocess.run(['python3', str(ROOT/'scripts/verify-a6-stock-audio.py')], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
blob = (ROOT/'build/audio-research/ios10/com.apple.driver.AppleEmbeddedAudio.macho').read_bytes()
codec = (ROOT/'build/audio-research/ios10/com.apple.driver.AppleCS42L65Audio.macho').read_bytes()
base = 0x8103e000
vtable = 0x8103eb8e + struct.unpack_from('<i',codec,0xb94)[0] + 8
assert vtable == 0x8104413c
assert struct.unpack_from('<I',codec,vtable-base+0x57c)[0] == 0x80a39659
assert struct.unpack_from('<I',codec,vtable-base+0x580)[0] == 0x80a3973d
assert codec[0x8103f28e-base:0x8103f294-base] == bytes.fromhex('052120469047')
assert codec[0x8103f298-base:0x8103f29c-base] == bytes.fromhex('a02811d1')

for register in (5,0x243,0xc804,0x9901):
 for writing in (False,True):
  u = Uc(UC_ARCH_ARM,UC_MODE_THUMB)
  u.mem_map(0x80a32000,0x30000);u.mem_write(0x80a32000,blob)
  u.mem_map(0x100000,0x100000)
  def word(a,v):u.mem_write(a,struct.pack('<I',v))
  obj,device,table=0x100000,0x101000,0x102000
  word(obj+0xc4,device);word(device,table);word(table+0x35c,0x103001)
  transfers=[]
  def hook(uc,a,size,data):
   if a!=0x103000:return
   q=[uc.reg_read(k) for k in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
   stack=uc.reg_read(UC_ARM_REG_SP)
   tx=bytes(uc.mem_read(q[1],q[2]));rxlen=struct.unpack('<I',uc.mem_read(stack,4))[0]
   transfers.append((tx,rxlen))
   if not writing:uc.mem_write(q[3],b'\x00\x00\x00\x00\xa0')
   uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  for reg,value in [(UC_ARM_REG_R0,obj),(UC_ARM_REG_R1,register),(UC_ARM_REG_R2,0x35),(UC_ARM_REG_SP,0x1f0000),(UC_ARM_REG_LR,0x1e0001)]:u.reg_write(reg,value)
  u.emu_start((0x80a39658 if writing else 0x80a3973c)|1,0x1e0000,count=10000)
  assert u.reg_read(UC_ARM_REG_PC)==0x1e0000
  header=bytes([0x6c if writing else 0x6d,register>>8,register&0x7f,0])
  assert transfers==[(header+(b'\x35' if writing else b''),0 if writing else 5)],transfers
  if not writing:assert u.reg_read(UC_ARM_REG_R0)==0xa0
print('PASS: stock codec vtable, register05 revision A0 branch, page-aware SPI read/write framing and fifth-byte reply')

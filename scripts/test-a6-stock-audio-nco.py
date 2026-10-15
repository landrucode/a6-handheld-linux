#!/usr/bin/env python3
"""Execute the owner's pinned stock NCO setter offline; no device access."""
import subprocess,pathlib,struct,hashlib
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
subprocess.run(['python3','scripts/verify-a6-stock-touch-pwm.py'],check=True,stdout=subprocess.DEVNULL)
p=pathlib.Path('build/touch-research/ios10-clock-dependencies/com.apple.driver.AppleS5L8950X.macho');b=p.read_bytes()
assert hashlib.sha256(b).hexdigest()=='282169637accffa96a7fd44d17ee524f5fc69179b8b541b98ba252b697c17d90'
for frequency in (3072000,12288000):
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.mem_map(0x8114b000,0x10000);u.mem_write(0x8114b000,b);u.mem_map(0x100000,0x100000)
 def w(a,v):u.mem_write(a,struct.pack('<I',v))
 def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 obj=0x100000;vt=0x101000;provider=0x102000;events=[]
 w(obj,vt);w(obj+0x1a8,provider);w(provider,vt)
 for offset,address in ((0x494,0x103001),(0x490,0x103021),(0x354,0x103041),(0x348,0x103061)):w(vt+offset,address)
 def hook(uc,a,size,data):
  if a==0x103000:events.append((uc.reg_read(UC_ARM_REG_R1),uc.reg_read(UC_ARM_REG_R2)));ret();return
  if a in (0x103020,0x103040):ret();return
  if a==0x103060:ret(342000000);return
 u.hook_add(UC_HOOK_CODE,hook)
 for k,v in ((UC_ARM_REG_R0,obj),(UC_ARM_REG_R1,6),(UC_ARM_REG_R2,frequency),(UC_ARM_REG_R3,1),(UC_ARM_REG_SP,0x1f0000),(UC_ARM_REG_LR,0x1e0001)):u.reg_write(k,v)
 u.emu_start(0x8114e15d,0x1e0000,count=10000)
 assert u.reg_read(UC_ARM_REG_PC)==0x1e0000
 assert (0x314,2*frequency) in events
 assert (0x318,(2*frequency-342000000)&0xffffffff) in events
 assert [v for a,v in events if a==0x310][:5]==[0x82000000,0x92000000,0x92000400,0x92000c00,0x92000800]
 print('PASS: stock NCO6 requested',frequency,'Hz uses doubled operand',2*frequency)

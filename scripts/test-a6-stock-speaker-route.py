#!/usr/bin/env python3
"""Execute pinned stock route code with explicit endpoint choices, offline.
No device access, MMIO, or coprocessor execution; model writes are RAM only.
"""
import subprocess
subprocess.run(["python3","scripts/verify-a6-stock-audio.py"],check=True,stdout=subprocess.DEVNULL)
from unicorn import *
from unicorn.arm_const import *
import struct,pathlib,hashlib
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
for base,size,path in [(0x80594000,0x40000,'build/audio-research/dma-platform-followup/com.apple.driver.AppleARMPlatform.macho'),(0x810bd000,0x8000,'build/audio-research/ios10/com.apple.driver.AppleAE2Audio.macho')]:
 u.mem_map(base,size);d=pathlib.Path(path).read_bytes()
 if base==0x80594000:assert hashlib.sha256(d).hexdigest()=='8087110ae6ce1491538e1dc7d4e4983e01f8cc673f66fb4732a62da7e52d13a5'
 u.mem_write(base,d[:size])
u.mem_map(0x80300000,0x100000);u.mem_map(0x80450000,0x10000);u.mem_map(0x100000,0x100000)
def w(a,v):u.mem_write(a,struct.pack('<I',v))
def r(a):return struct.unpack('<I',u.mem_read(a,4))[0]
obj=0x100000;entries=0x101000;matrix=0x102000;regs=0x103000;fun=0x104000;params=0x105000;sp=0x1f0000;heap=0x120000
w(obj,0x810c3880);w(obj+0x50,16);w(obj+0x54,21);w(obj+0x58,0x106000);w(obj+0x5c,entries);w(obj+0x60,matrix);w(obj+0x6c,regs);w(obj+0x70,5);w(obj+0x74,4);w(obj+0x78,5)
baseline=[0]*21
for i,v in enumerate(baseline):w(regs+4*i,v)
names=[0x64737030+i for i in range(4)]+[0x64737063]+[0x70696e30+i for i in range(5)]+[0x61756430+i for i in range(4)]+[0x6d636130+i for i in range(2)]
for i,n in enumerate(names):
 w(entries+12*i,n);w(entries+12*i+4,0x107000);w(entries+12*i+8,3 if n>>8==0x70696e or n==0x64737063 else 0)
w(0x107000,0x108000);w(0x108050,0x109021);w(0x108014,0x109001);w(0x108070,0x109001);u.mem_write(0x109000,b'\x70\x47');w(fun+0x14,obj);w(fun+0x18,params);w(params,0x6d636130);w(params+4,0x70696e32);w(params+8,0x30303)
# getEndpointName logging only, plus allocation/lock/memory imports.
skip={0x805bc7a8,0x805bc7b8,0x805bc7c8,0x805bcec8,0x805bce98,0x805bd088,0x805bc7e8}
def hook(uc,a,size,x):
 global heap
 if a==0x805af510:uc.reg_write(UC_ARM_REG_R0,0x107000);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
 if a in (0x109000,0x109020):uc.reg_write(UC_ARM_REG_R0,0x109100 if a==0x109020 else 0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
 if a==0x805bce88:
  p=heap;heap+=0x1000;w(p,0x108000);uc.reg_write(UC_ARM_REG_R0,p);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
 if a in (0x805bd118,0x805bd108):
  p=uc.reg_read(UC_ARM_REG_R0);q=uc.reg_read(UC_ARM_REG_R1)
  if a==0x805bd118:uc.mem_write(p,bytes(q))
  else:uc.mem_write(q,bytes(uc.mem_read(p,uc.reg_read(UC_ARM_REG_R2))))
  uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
 if a in skip or 0x80300000 <= a < 0x80400000:uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
 if a==0x805afdd0:
  pass
u.hook_add(UC_HOOK_CODE,hook)
# MCA route at810c0718..0730 selects flag2 when object+d8 is master.
# Previous flag1 selected the external-clock direction despite master config.
for source,packed,active,flags in [(0x61756432,0x300003,0,0x20),(0x6d636130,0x30303,3,2)]:
 w(params,source);w(params+8,packed)
 for reg,val in [(UC_ARM_REG_R0,fun),(UC_ARM_REG_R1,active),(UC_ARM_REG_R2,flags),(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,0x1e0001)]:u.reg_write(reg,val)
 u.emu_start(0x805ae995,0x1e0000,count=1000000)
 assert u.reg_read(UC_ARM_REG_PC)==0x1e0000 and u.reg_read(UC_ARM_REG_R0)==0
 pass
assert r(regs+8)==0xf014 and r(regs+0x24)==0x200 and r(regs+0x48)==1
print('PASS: MCA0 master serial route (stock flag2) and IIS2 MCLK coexist')

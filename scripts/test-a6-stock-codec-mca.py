import subprocess
subprocess.run(["python3","scripts/verify-a6-stock-audio.py"],check=True,stdout=subprocess.DEVNULL)
from unicorn import *
from unicorn.arm_const import *
import struct,pathlib,importlib.util
spec=importlib.util.spec_from_file_location('dt','scripts/inspect-a6-platform-tree.py');dt=importlib.util.module_from_spec(spec);spec.loader.exec_module(dt)
props=dt.parse_tree(pathlib.Path('build/touch-research/DeviceTree-ios10.raw').read_bytes())
for slots in (8,):
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
 for base,size,path in [(0x810bd000,0x8000,'build/audio-research/ios10/com.apple.driver.AppleAE2Audio.macho'),(0x80594000,0x40000,'build/audio-research/dma-platform-followup/com.apple.driver.AppleARMPlatform.macho')]:
  u.mem_map(base,size);u.mem_write(base,pathlib.Path(path).read_bytes()[:size])
 u.mem_map(0x100000,0x100000)
 def w(a,v):u.mem_write(a,struct.pack('<I',v))
 def r(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 obj=0x100000;fmt=0x101000;provider=0x102000;vt=0x103000;regs={};events=[]
 d=bytearray(props['/device-tree/arm-io/mca0/audio-codec-reference']['reg']);d[0]|=1;d[20:24]=struct.pack('<I',255);d[24:28]=struct.pack('<I',0);d[28]=8;d[29]=0;d[16:20]=struct.pack('<HH',48,1);d[30:32]=bytes([16,16])
 u.mem_write(fmt,bytes(d));w(obj+0xbc,provider);w(obj+0x84,provider);w(provider,vt);w(vt+0x3c,0x104001);w(vt+0x34c,0x104021);w(obj+0x98,128);w(obj+0x9c,128)
 def hook(uc,a,size,x):
  q=[uc.reg_read(k) for k in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
  if a==0x104000:events.append(('clock_request',r(q[1])));ret();return
  if a==0x104020:uc.reg_write(UC_ARM_REG_R1,0);ret(342000000);return
  if a==0x810c1618:regs[q[1]]=q[2];events.append(('write',q[1]*4,q[2]));ret();return
  if a==0x810c15c4:ret(0);return
  if a==0x810c20ec:ret();return
 u.hook_add(UC_HOOK_CODE,hook)
 for k,v in [(UC_ARM_REG_R0,obj),(UC_ARM_REG_R1,fmt),(UC_ARM_REG_SP,0x1f0000),(UC_ARM_REG_LR,0x1e0001)]:u.reg_write(k,v)
 u.emu_start(0x810bfbfd,0x1e0000,count=100000)
 assert u.reg_read(UC_ARM_REG_PC)==0x1e0000
 assert events[0]==('clock_request',12288000)
 assert [regs[i] for i in (2,3,4,5,6,7,8,9,11,12,13,14)]==[0x1010,0x0f107005,1,0,0x208,0xd,0x007b0004,255,0x10a,0xd,0x00030004,0]
 print('PASS: stock layout0 MCA0 reference format, eight16-bit TX slots, RX disabled, 12.288MHz NCO request')

#!/usr/bin/env python3
"""Extract the bounded candidate amp sequence from the owner’s pinned stock files.

Requires Unicorn locally. Output remains under ignored build/, mode 600.
Endpoint inputs are explicit candidate choices: 48 kHz, 16-bit, channel0
spF0 (flag monitor), amplifier clock slave to MCA0, with VMON/IMON serial monitor channels;
they are not a captured iOS stream.
"""
import os, subprocess, sys
master = "--amp-master" in sys.argv
supply = "--supply-monitors" in sys.argv
stock44100 = "--stock44100" in sys.argv
if stock44100 and (not master or supply):raise SystemExit("--stock44100 requires --amp-master without supply monitors")
os.umask(0o077)
subprocess.run(["python3", "scripts/verify-a6-stock-audio.py"], check=True, stdout=subprocess.DEVNULL)
from unicorn import *
from unicorn.arm_const import *
import pathlib,struct,importlib.util,json
spec=importlib.util.spec_from_file_location('dt','scripts/inspect-a6-platform-tree.py');dt=importlib.util.module_from_spec(spec);spec.loader.exec_module(dt)
props=dt.parse_tree(pathlib.Path('build/touch-research/DeviceTree-ios10.raw').read_bytes())['/device-tree/arm-io/i2c0/audio-speaker']
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
for base,size,path in [(0x80db1000,0x10000,'ios10/com.apple.driver.AppleCS35L19Amp.macho'),(0x80a32000,0x30000,'ios10/com.apple.driver.AppleEmbeddedAudio.macho')]:
 u.mem_map(base,size);u.mem_write(base,pathlib.Path('build/audio-research/'+path).read_bytes())
u.mem_map(0x100000,0x100000);u.mem_map(0x80300000,0x100000)
if stock44100:u.mem_map(0,4096)
def w(a,v):u.mem_write(a,struct.pack('<I',v))
def r(a):return struct.unpack('<I',u.mem_read(a,4))[0]
obj=0x100000;cfg=0x101000;rev=0x102000;types=0x103000;events=[];regs={5:0xb0};phase='';unknown=[]
w(obj,0x80db5110);w(obj+0xf0,1);w(obj+0xdc,rev);w(obj+0x11c,cfg);w(obj+0xd8,types);w(types,0x80db4df4);w(obj+0xe0,0);u.mem_write(cfg,props['speaker-config']);u.mem_write(rev,b'\xb0')
# getMasterIndex (vtable+394 -> 80a340a8) reads object+a0. Stock
# 80db2dfc compares it with this endpoint index; 80db2976 selects03/43.
# Explicit candidate: MCA0 generates clocks, so the amp must not claim them.
w(obj+0xa0,0 if master else 0xffffffff)
if stock44100:
 # N42 has function-alive. Keep this stock branch live; model only its
 # GPIO/timer callbacks, retaining every actual amplifier register write.
 w(obj+0xfc,0x107000);w(obj+0x100,0x108000);w(0x108000,0x109000);w(0x109074,0x10a001);w(0x1090a0,0x10a021)
 w(obj+0xe4,0x104000);w(0x104000,0x105000);w(0x10503c,0x106001)
# Disable logging, whose globals otherwise point into unloaded kernel data.
for a in (0x80db37c6,0x80db3f6c,0x80db27e2,0x80db2af4,0x80db4064,0x80db408a,0x80db4310,0x80db4532,0x80db4620):pass
# Resolve all amp PC-relative data references landing at global pointers.
# An import logger hook avoids dereference only after the global; populate
# every zero pointer in the writable data section with a valid zero word.
zero=0x10f000
# Kernel external global pointers referenced through local GOT cells.
def missing(uc,access,address,size,value,data):
 if access==UC_MEM_READ_UNMAPPED and address>=0x80000000:
  uc.mem_map(address&~4095,4096);return True
 return False
u.hook_add(UC_HOOK_MEM_READ_UNMAPPED,missing)
def ret(v=0):u.reg_write(UC_ARM_REG_R0,v);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
def hook(uc,a,size,x):
 global phase
 q=[uc.reg_read(k) for k in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)];sp=uc.reg_read(UC_ARM_REG_SP)
 if a in (0x80a38df8,0x80a392f8,0x80a392bc,0x80a3938e,0x80a38f2c):
  if a==0x80a38f2c:events.append([phase,'read',q[2],regs.get(q[2],0)]);ret(regs.get(q[2],0));return
  if a in (0x80a38df8,0x80a392bc):reg=q[2];val=q[3]
  else:reg=q[1];val=q[2]
  if a in (0x80a392bc,0x80a3938e):mask=val;val=(regs.get(reg,0)&~mask)|(r(sp) if a==0x80a392bc else q[3]);events.append([phase,'mask',reg,mask,val,r(sp) if a==0x80a392bc else q[3]])
  else:events.append([phase,'write',reg,val])
  regs[reg]=val&255;ret(0);return
 if stock44100 and a==0x80db2448:events.append([phase,'alive_kick']);ret();return
 if stock44100 and a in (0x10a000,0x10a020):events.append([phase,'alive_timer',int(a==0x10a000)]);ret();return
 if a==0x80db4ac0:ret(0);return # isMetaClass: not Bluetooth endpoint
 if a==0x80a351d4:ret(1);return # live data endpoint, direction mask0/1 supported
 if a==0x80a35e4c:ret(0);return # channel index derived descriptor
 if a==0x80a35e56:ret(16);return
 if a==0x80a35158:uc.reg_write(UC_ARM_REG_R1,44100 if stock44100 else 48000);ret(0);return
 if a==0x80a34e38 and stock44100:ret({0:0x73705630,1:0x73704930}.get(q[2],0) if q[1]==0x171 else 0);return
 if a==0x80a34e38:ret({0:0x73704630,1:0x73705630,2:0x73704930,3:0x73705030 if supply else 0,4:0x73704230 if supply else 0}.get(q[2],0) if q[1]==0x171 else 0);return
 if a==0x80db4cd0:uc.mem_write(q[0],bytes(q[1]));ret();return
 if a==0x80db4d00:events.append([phase,'deadline_ns',q[0]*q[1]]);w(q[2],1);w(q[2]+4,0);ret();return
 if a==0x80db4ce0:events.append([phase,'wait_deadline']);ret();return
 if a==0x80db4a40:events.append([phase,'sleep_ms',q[0]]);ret();return
 if a in (0x80db4d10,0x80db4d30,0x8031f078):ret();return
 if a==0x106000 and stock44100:events.append([phase,'mclk_hz',r(q[1])]);ret(0);return
 if a==0x80db36d8 and not stock44100:events.append([phase,'mclk',q[1]]);ret(1);return
 if a==0x80db2678:events.append([phase,'reset',q[1]]);ret();return
 if a==0x80a35e60:ret(0);return
 if 0x10f000<=a<0x1e0000:raise RuntimeError('unmodeled data execution '+hex(a))
 if a<0x100000 or (0x200000<=a<0x80a31000) or 0x80a61000<=a<0x80db1000 or a>=0x80dc1000:raise RuntimeError('unmodeled PC '+hex(a))
u.hook_add(UC_HOOK_CODE,hook)
for addr,name,arg in [(0x80db37b4,'reset_init',0),(0x80db3f60,'format_init',1),(0x80db4528,'power_state',0),(0x80db4054,'power_config',1),(0x80db4300,'status_init',0),(0x80db3b60,'play_enable',0),(0x80db4610,'shutdown',0)]:
 phase=name
 for k,v in [(UC_ARM_REG_R0,obj),(UC_ARM_REG_R1,arg),(UC_ARM_REG_SP,0x1f0000),(UC_ARM_REG_LR,0x1e0001)]:u.reg_write(k,v)
 try:u.emu_start(addr|1,0x1e0000,count=1000000)
 except UcError as e:raise RuntimeError(name+' PC '+hex(u.reg_read(UC_ARM_REG_PC))) from e
 assert u.reg_read(UC_ARM_REG_PC)==0x1e0000,name
 pass
p=pathlib.Path('build/audio-research/amp-'+('stock44100-' if stock44100 else '')+('supply-' if supply else '')+('master-' if master else '')+'sequence.private.json');p.write_text(json.dumps({'assumptions':'44.1kHz amp-master candidate with VMON/IMON slots0/1, inferred from observed MCA descriptor; function-alive branch included; amp writes derived by stock emulation, not captured live' if stock44100 else 'candidate explicitly requests 48kHz/16-bit, flag role spF0 in channel0; DAC RX defaults to slot0, matched clock role, VMON/IMON serial monitor channels; factory calibration absent','rate_hz':44100 if stock44100 else 48000,'clock_master':master,'monitor_slots':[0,1] if stock44100 else [1,2],'events':events},indent=2));p.chmod(0o600)

ops=[];shutdown=0
for e in events:
 if e[0]=='reset_init':continue
 if e[0]=='shutdown' and not shutdown:shutdown=len(ops)
 kind=e[1]
 if kind=='write':ops.append((2,e[2],255,e[3]))
 elif kind=='mask':ops.append((3,e[2],e[3],e[5]))
 elif kind=='alive_kick':ops.append((5,0,0,0))
 elif kind=='alive_timer':ops.append((6,0,0,e[2]))
 elif kind=='read':ops.append((1,e[2],0,0))
 elif kind=='sleep_ms':ops.append((4,0,0,e[2]))
 elif kind=='wait_deadline':ops.append((4,0,0,10))
 elif kind not in ('deadline_ns','mclk','mclk_hz','reset'):raise ValueError(e)
assert shutdown and len(ops)<128
if stock44100:
 assert [e[2] for e in events if e[1]=='mclk_hz']==[12000000,0]
 assert len([e for e in events if e[0]=='play_enable' and e[1]=='alive_kick'])==3
 assert [e[2] for e in events if e[1]=='alive_timer']==[0,1]
 assert any(e[0]=='play_enable' and e[1]=='mask' and e[2:]==[10,15,5,5] for e in events)
 assert any(e[0]=='play_enable' and e[1]=='mask' and e[2]==12 and e[3]==8 and e[5]==0 for e in events)
assert any(e[:3]==['play_enable','write',0x2d] and e[3]==(0 if stock44100 else 2) for e in events)
assert any(e[:3]==['play_enable','write',0x2e] and e[3]==(2 if stock44100 else 4) for e in events)
# Stock power state matches the requested monitor roles; DAC RX remains enabled.
assert any(e[:3]==['play_enable','write',7] and e[3]==(0 if supply else 0x30) for e in events)
assert [e[3] for e in events if e[1]=='write' and e[2]==0x0d]==([0x43,0x43] if master else [3,3])
lines=['/* Generated from owner stock; private, never commit. */',
 'static const unsigned char a6_at_config[20] = {'+', '.join(str(v) for v in props['speaker-config'])+'};',
 'static const unsigned char a6_at_ops[][4] = {']
lines.extend('{'+','.join(str(v) for v in op)+'},' for op in ops)
lines.extend(['};', '#define A6_AT_SHUTDOWN '+str(shutdown)])
p=pathlib.Path('build/audio-research/amp-tone-sequence.private.inc')
if master or supply:
 lines=[line for line in lines if not line.startswith('static const unsigned char a6_at_config')]
 suffix=('stock44100_' if stock44100 else '')+('supply_' if supply else '')+('master_' if master else '')
 lines=[line.replace('a6_at_ops', 'a6_at_'+suffix+'ops').replace('A6_AT_SHUTDOWN', 'A6_AT_'+suffix.upper()+'SHUTDOWN') for line in lines]
 with p.open('a') as out: out.write('\n'.join(lines)+'\n')
else:
 p.write_text('\n'.join(lines)+'\n')
p.chmod(0o600)
print('Prepared private stock amp operations:',len(ops),'shutdown index:',shutdown)

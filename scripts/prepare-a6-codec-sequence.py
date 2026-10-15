#!/usr/bin/env python3
"""Generate private B1 receiver operations by executing pinned stock code."""
import json
import os
import subprocess
import runpy
from pathlib import Path
os.umask(0o077)
subprocess.run(['build/audio-research/trace-venv/bin/python','scripts/test-a6-stock-codec-profile.py'],check=True)
data=json.loads(Path('build/audio-research/codec-b1-mca-vsp.private.json').read_text())
mca=runpy.run_path('scripts/test-a6-stock-codec-mca.py')['regs']
profile=[mca[i] for i in (2,3,4,5,6,7,8,9,11,12,13,14)]
arrays={name:[] for name in ('muted_init','receiver_enable','receiver_mute')}
registers=[]
for event in data['events']:
    phase,kind,*args=event
    if phase not in arrays:continue
    if kind=='write':ops=[(args[0],0,255,args[1])]
    elif kind=='mask':ops=[(args[0],1,args[1],args[2])]
    elif kind=='block_write':ops=[(args[0]+i,0,255,v) for i,v in enumerate(bytes.fromhex(args[1]))]
    elif kind=='sleep':ops=[(0,2,0,args[0])]
    elif kind in ('read','block_read','clock_enable','generic_reset','port_count','vsp_direction_flags','control','channel_role','channel_control','mikey_state'):continue
    else:raise ValueError(event)
    arrays[phase].extend(ops)
    for reg,op,mask,value in ops:
        assert value<=255 and (op==2 or not reg&0x80),event
        if op!=2 and reg not in registers:registers.append(reg)
# Stock shutdown81040aa6 powers down after muting, before MCLK removal.
if 6 not in registers:registers.append(6)
assert len(registers)<128 and all(len(ops)<128 for ops in arrays.values())
lines=['/* Owner stock generated operations: private, never commit. */',
       'static const u32 a6_ac_mca_config[]={'+','.join(hex(v) for v in profile)+'};',
       'static const u32 a6_ac_profile_registers[]={'+','.join(hex(v) for v in registers)+'};']
for name,ops in arrays.items():
    lines.append('static const u32 a6_ac_'+name+'[][4]={')
    lines.extend('{'+','.join(hex(v) for v in op)+'},' for op in ops)
    lines.append('};')
p=Path('build/audio-research/codec-receiver-sequence.private.inc')
p.write_text('\n'.join(lines)+'\n');p.chmod(0o600)
print('PASS: private codec sequence:',len(registers),'preimages;', {k:len(v) for k,v in arrays.items()})

env=os.environ.copy();env['A6_CODEC_REFERENCE_ONLY']='1'
subprocess.run(['build/audio-research/trace-venv/bin/python','scripts/test-a6-stock-codec-profile.py'],env=env,check=True)
events=json.loads(Path('build/audio-research/codec-b1-mca-xsp-reference.private.json').read_text())['events']
ops=[];reference_regs=[]
for phase,kind,*args in events:
 if phase!='muted_init':continue
 if kind=='write':items=[(args[0],0,255,args[1])]
 elif kind=='mask':items=[(args[0],1,args[1],args[2])]
 elif kind=='block_write':items=[(args[0]+i,0,255,v) for i,v in enumerate(bytes.fromhex(args[1]))]
 elif kind=='sleep':items=[(0,2,0,args[0])]
 else:continue
 ops.extend(items)
 for reg,op,mask,value in items:
  assert value<=255 and (op==2 or not reg&0x80)
  if op!=2 and reg not in reference_regs:reference_regs.append(reg)
for reg in reference_regs:
 if reg not in registers:registers.append(reg)
assert len(registers)<128
s=p.read_text();start=s.index('static const u32 a6_ac_profile_registers[]=');end=s.index('\n',start)
s=s[:start]+'static const u32 a6_ac_profile_registers[]={'+','.join(hex(v) for v in registers)+'};'+s[end:];p.write_text(s)
with p.open('a') as f:
 f.write('static const u32 a6_ac_reference_init[][4]={\n')
 for op in ops:f.write('{'+','.join(hex(v) for v in op)+'},\n')
 f.write('};\n')
print('PASS: stock XSP reference RX only, output muted, restore coverage')

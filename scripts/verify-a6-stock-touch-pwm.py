#!/usr/bin/env python3
"""Pin the stock n42 PWM dispatch, fixed clock source and trial arithmetic."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
repo=Path(__file__).resolve().parents[1]
def load(name,base,digest):
 p=repo/'build/touch-research/ios10-clock-dependencies'/('com.apple.driver.'+name+'.macho')
 d=p.read_bytes();assert hashlib.sha256(d).hexdigest()==digest,name
 def raw(addr,n):
  off=addr-base;assert 0<=off<=len(d)-n
  return d[off:off+n]
 return raw
arm=load('AppleARMPlatform',0x80594000,'8087110ae6ce1491538e1dc7d4e4983e01f8cc673f66fb4732a62da7e52d13a5')
soc=load('AppleS5L8950X',0x8114b000,'282169637accffa96a7fd44d17ee524f5fc69179b8b541b98ba252b697c17d90')
pwm=load('AppleS5L8920XPWM',0x8084b000,'b715106761c7bb3608bc7d91e2c3eac2213025507bffdda02ee27cead3afc105')
def word(read,addr):return struct.unpack('<I',read(addr,4))[0]
def expect(read,addr,hexbytes):
 b=bytes.fromhex(hexbytes);assert read(addr,len(b))==b,hex(addr)
# Constructor-installed vtables, not guessed offsets from nearby functions.
assert 0x80599f2a+word(arm,0x80599f30)+8==0x805c8b5c
assert word(arm,0x805c8b5c+0x34c)==0x8059a06b
assert 0x805a5e4e+word(arm,0x805a5e60)+8==0x805ccd58
assert word(arm,0x805ccd58+0x354)==0x805a6091
assert word(arm,0x805ccd58+0x344)==0x805a6125
assert 0x8114c30e+word(soc,0x8114c314)+8==0x81150100
assert word(soc,0x81150100+0x348)==0x80599e59
assert word(soc,0x81150100+0x34c)==0x8114cadd
assert word(pwm,0x8084c088+0x344)==0x8084b731
assert word(pwm,0x8084c088+0x34c)==0x805a5c85
assert word(pwm,0x8084c088+0x348)==0x8084b745
expect(arm,0x805a5cbe,'d4f84843')
# nclk name is slot4; corresponding frequency comes from gPE+90/+94.
assert 0x8114c652+word(soc,0x8114c8d4)==0x8114f787
assert soc(0x8114f787,5)==b'nclk\0'
expect(soc,0x8114c692,'d1f89020d1f8941041620262')
assert 0x8114c670+word(soc,0x8114c8dc)==0x811500c8
assert word(soc,0x811500c8)==0x80456a80
# Verify matching kernel's property parser, not just a newer XNU structure.
k=(repo/'build/touch-research/Kernelcache-ios10.raw').read_bytes()
assert hashlib.sha256(k).hexdigest()=='bbc90ec2bd9ce1cc43c6a98b47d39348d63443b5d6c22293f23a1f43bebe4b46'
kr=lambda a,n:k[a-0x80001000:a-0x80001000+n]
assert kr(0x803cf8bf,16)==b'fixed-frequency\0'
expect(kr,0x8036f86c,'40f24702c0f206027a44')
assert 0x8036f878+0x60047==0x803cf8bf
expect(kr,0x8036f8b0,'c8f89410c8f89000')
# pwmC uses flag0 at stack0 and continuous-count pair(0,1) at stack4/8.
# Do not mistake the high count word1 for the Boolean mode argument.
assert arm(0x805a6478,4)==b'Cmwp'
expect(arm,0x805a645c,'012002900020cde9000000224046b047')
expect(arm,0x805a60aa,'f8683969ba688df82f20cde90801')
expect(arm,0x805a619e,'bc6824780494cde90256cde900cec847')
expect(arm,0x805a5cb0,'d7f80c90d7f808c0d7f818e00468d4f84843cdf808e0cde900c9a047')
expect(arm,0x805a5f28,'4ff00040') # half-scale default duty
expect(arm,0x805a60c4,'5fea56024fea3503c01851412a463346')
expect(arm,0x805a60d8,'a0fb082301fb083312f1004243f10002')
expect(pwm,0x8084b78c,'44f20305bbf1000f18bf44f20725')
# Exact board properties ensure no optional override changes the recipe.
inv=json.loads(subprocess.check_output(['python3',str(repo/'scripts/inspect-a6-touch-tree.py'),str(repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw')]))
nodes={n['path']:n['properties'] for n in inv['nodes']}
g=nodes['/device-tree/arm-io/pwm/grape-clk'];p=nodes['/device-tree/arm-io/pwm']
assert g['reg']['le32']==[2] and g['default-hz']['le32']==[32768]
assert p['clock-ids']['le32']==[4]
for key in ('duty-cycle','calibration-data','enable-ms','intensity-config'):assert key not in g
assert nodes['/device-tree/arm-io/spi1/multi-touch']['function-clock_enable']['hex']=='00000037436d7770'
period=(24000000+32768//2)//32768
high=(period*0x80000000+0x80000000)>>32
assert (period,high,period-high)==(732,366,366)
print(json.dumps({'stock_dispatch_verified':True,'source':'CPU0 fixed-frequency via gPEClockFrequencyInfo+0x90 and legacy nclk ID4','accepted_source_hz':24000000,'target_hz':32768,'period':period,'high':high,'low':period-high,'control':'0x4003','nominal_output_hz':24000000/period,'limitation':'Register recipe and firmware frequency only; external waveform and touchscreen response require hardware testing.'},indent=2))

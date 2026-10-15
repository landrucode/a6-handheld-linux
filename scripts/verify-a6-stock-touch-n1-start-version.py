#!/usr/bin/env python3
"""Pin the exact N1 startup hook and its ordering before reset deassertion."""
from pathlib import Path
import hashlib, json, struct
repo=Path(__file__).resolve().parents[1]
p=repo/'build/touch-research/AppleMultitouchSPI-ios10.macho'
b=p.read_bytes()
assert hashlib.sha256(b).hexdigest()=='bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0'
def raw(a,n): return b[a-0x80854000:a-0x80854000+n]
def word(a): return struct.unpack('<I',raw(a,4))[0]
def expect(a,h): assert raw(a,len(bytes.fromhex(h)))==bytes.fromhex(h),hex(a)
v=0x808684d4
assert word(v+0x528)==0x8086159d
# 19,c1; slot35c; two TX/two RX; delay literal 10.
expect(0x808615a8,'192007f8160cc12007f8150c')
expect(0x808615c8,'606d0168d1f85c53')
expect(0x808615d4,'02260096')
expect(0x808615e0,'022241465346a847')
expect(0x808615fc,'0a2001f0a5fa')
# Generic start calls slot528, then slot4f4. N1 maps slot4f4 to reset control.
expect(0x8085d160,'2068d0f8281520468847')
expect(0x8085d16a,'2068d0f8f424012120469047')
assert word(v+0x4f4)==0x8085d385
print(json.dumps({'startup_hook':hex(word(v+0x528)),'startup_tx':'19c1','tx_bytes':2,'rx_bytes':2,'delay_argument':10,'ordering':'slot528 completes before reset slot4f4 is called'},indent=2))

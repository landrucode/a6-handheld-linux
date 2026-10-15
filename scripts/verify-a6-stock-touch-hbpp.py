#!/usr/bin/env python3
"""Pin the N1 bootloading caller and its HBPP probe/response contract."""
from pathlib import Path
import hashlib, json, struct
repo = Path(__file__).resolve().parents[1]
b = (repo/'build/touch-research/AppleMultitouchSPI-ios10.macho').read_bytes()
assert hashlib.sha256(b).hexdigest() == 'bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0'
def raw(a,n): return b[a-0x80854000:a-0x80854000+n]
def word(a): return struct.unpack('<I',raw(a,4))[0]
def expect(a,h): assert raw(a,len(bytes.fromhex(h))) == bytes.fromhex(h),hex(a)
# Instance constructor, not metaclass constructor. Generic CHECK is inherited
# but the N1 bootloading entry actually invokes a different slot, 0x520.
expect(0x80861470,'0249794408310160')
v = 0x80861476 + word(0x8086147c) + 8
assert v == 0x808684d4
assert word(v+0x368) == 0x8085d6e1
assert word(v+0x520) == 0x8085dc85
expect(0x8085d6e8,'2068d0f8201520468847')
# Fixed 1a a1 prefix, followed by seven 18 e1 pairs, 16 TX and 16 RX.
expect(0x8085dca0,'1a208df85c00a1208df85d00022017ad1821e1222b1829545a7002301028f9d3')
expect(0x8085dce2,'d8f854000168d1f85c43cde90166102600960df14c0a102229465346a047')
# First and second BE16 response words separately enter identical allowlists.
expect(0x8085dd20,'9df84c209df84d309df84e009df84f1043ea0222')
expect(0x8085dd52,'41f6e1039a421cbf41f6a1239a420ad041f6017305e0')
expect(0x8085dd78,'41ea00204ff0010a')
expect(0x8085dd9e,'41f6e10188421cbf41f6a12188424fd041f6017105e0')
# Pin remaining accepted constants and decision branches, including rejection.
expect(0x8085dd44,'44f679039a4215d044f6691310e0')
expect(0x8085dd68,'44f6c1339a4203d044f6d1239a4225d1')
expect(0x8085dd90,'44f6790188425ad044f6691110e0')
expect(0x8085ddb4,'44f6d121884248d044f6c131884244d0')
# Optional download GPIO does not exist on n42; slot500 resolves that name.
assert raw(0x8085d5e0+word(0x8085d63c),25) == b'function-enable_download\0'
print(json.dumps({'n1_vtable':hex(v),'hbpp_probe':hex(word(v+0x520)),
 'tx':'1aa1'+'18e1'*7,'rx_bytes':16,
 'accepted_each_of_first_two_be16':['18e1','1aa1','1f01','4879','4969','4ad1','4bc1'],
 'prior_1f011f01_matches_hbpp_prefix':True,
 'limitation':'Prior command was generic CHECK; exact HBPP hardware probe still required.'},indent=2))

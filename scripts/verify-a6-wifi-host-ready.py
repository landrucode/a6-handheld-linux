#!/usr/bin/env python3
"""Verify N42 host-ready GPIO dispatch offline; emit derived metadata only."""
from pathlib import Path
import hashlib, importlib.util, json, struct, subprocess
ROOT = Path(__file__).resolve().parents[1]
b = (ROOT/'build/touch-research/ios10-touch-dependencies/com.apple.driver.AppleS5L8930X.macho').read_bytes()
assert hashlib.sha256(b).hexdigest() == '08016671a8a5ad527c1e6c1485163d400ae9c75f9a728d370e1f629ced42a30b'
def raw(a,n): return b[a-0x81141000:a-0x81141000+n]
def word(a): return struct.unpack('<I',raw(a,4))[0]
def expect(a,h): assert raw(a,len(bytes.fromhex(h))) == bytes.fromhex(h),hex(a)
# Reuse the full audited descriptor-copy, polarity and provider dispatch proof.
subprocess.run(['python3',str(ROOT/'scripts/verify-a6-stock-touch-gpio-cs.py')],check=True,stdout=subprocess.DEVNULL)
assert word(0x81146920+0x37c) == 0x81142947
expect(0x81142b42,'226a130a0d6f0020ab4211d202f0f803072b0dd802f0070040ea52102062')
expect(0x811428b6,'4ff6ff724a40d4f8803033f81a60324000ea0100104323f81a002168d1f87c334fea8a0182b220469847')
expect(0x81142946,'406e42507047')
spec=importlib.util.spec_from_file_location('topology',ROOT/'scripts/inspect-a6-platform-tree.py')
adt=importlib.util.module_from_spec(spec);spec.loader.exec_module(adt)
sources=[]
for name,digest in [('.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw','a51e5bdc3609f18cfa9e78e1f9f866f19d328a09fe61fbde9d74c056b89eecef'),('build/touch-research/DeviceTree-ios10.raw','9dfa77a3e1db226a304abb643dc829ed2e7d305beebfdc67d965eb255837736d')]:
 data=(ROOT/name).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
 nodes=adt.parse_tree(data);p=nodes['/device-tree/arm-io/usb-complex/usb-ehci/wlan']['function-host_ready']
 assert len(p)==16 and p[4:8]==bytes.fromhex('4f495047')
 owners=[path for path,props in nodes.items() if props.get('AAPL,phandle')==p[:4]]
 assert owners==['/device-tree/arm-io/gpio']
 assert struct.unpack('<I',p[8:12])[0]==0x606 and p[12:]==bytes.fromhex('01010000')
 assert struct.unpack('<II',nodes[owners[0]]['reg'])==(0xfa00000,0x1000)
 assert struct.unpack('<III',nodes['/device-tree/arm-io']['ranges'])==(0,0x30000000,0x10000000)
 sources.append(name)
pin=(0x606 & 7)|(0x606 >> 5);assert pin==54
assert (1 ^ 1 ^ 1)==1 and (0 ^ 1 ^ 1)==0
print(json.dumps({'stock_trees':sources,'gpio_provider_sha256':hashlib.sha256(b).hexdigest(),
 'linear_pin':pin,'register_physical':'0x3fa000d8','polarity':'logical request equals physical level',
 'output_mask':'0x6f','low_value':'0x2','high_value':'0x3',
 'stock_cache_mask_width':16,'MMIO_store_width':32,
 'candidate_requirement':'Preserve unrelated register bits and restore saved full register with final readback.',
 'hardware_writes':0},indent=2))

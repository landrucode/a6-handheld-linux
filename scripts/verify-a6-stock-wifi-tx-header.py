#!/usr/bin/env python3
"""Verify pinned stock startBulkWrite header construction without exporting bytes."""
import hashlib
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'build/touch-research/ios10-wifi-kexts/com.apple.driver.AppleBCMWLANBusInterfaceHSIC.macho'
d=p.read_bytes()
assert hashlib.sha256(d).hexdigest()=='23d1a4b801ea634ea042059b64e5de380ae251a2dc00429b15bb24b5db7c88a8'
base=0x80c21000
# Host-side provenance checks of the instructions underlying the clean-room codec.
checks={
 0x80c26454:'21a810210022', # mbuf_prepend16
 0x80c26482:'00211022', # memset16 zero
 0x80c2648a:'a020707001203070', # flags low1/higha0 = a001
 0x80c26492:'0af11000', # payload bytes +16
 0x80c264a8:'b071010af171', # LE sequence at6/7
 0x80c264ec:'00eb1040c043b070000af070', # fold/complement and LE checksum at2/3
}
for addr,expected in checks.items():
 b=bytes.fromhex(expected);assert d[addr-base:addr-base+len(b)]==b,hex(addr)
print(json.dumps({'stock_kext_sha256':hashlib.sha256(d).hexdigest(),'tx_header_bytes':16,'tx_flags':'a001','tx_kind':2,'length_offset':4,'sequence_offset':6,'checksum_offset':2,'reserved_bytes_zero':True,'stock_instruction_checks':'passed','hardware_tx_proven':False},indent=2))

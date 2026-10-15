#!/usr/bin/env python3
"""Verify chain/padding and blob analysis without using private packet bytes."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=module('outer','analyze-a6-wifi-loopback-outer.py');rx=module('rx','a6-capture-wifi-rx-packet.py')
tx=rx.loopback_tx()
assert m.analyze(tx*2)['chain_walks'][0]['complete']
blob=m.analyze(b'\0'*176+tx+b'\0'*1600)
assert [h['offset'] for h in blob['valid_headers']]==[176]
assert not any(w['complete'] for w in blob['chain_walks'])
assert not blob['canonical_events'] and not blob['repeated_nonzero_blocks']
bad=bytearray(tx);bad[2]^=1;assert not m.analyze(bad)['valid_headers']
# A19-byte record followed by zero padding and another record.
record=bytearray(tx[:19]);record[2:4]=b'\0\0';record[4:6]=(19).to_bytes(2,'little')
s=sum(int.from_bytes(record[i:i+2],'little') for i in range(0,16,2));s=(s&65535)+(s>>16);record[2:4]=((~s)&65535).to_bytes(2,'little')
report=m.analyze(record+b'\0'+record+b'\0')
assert report['chain_walks'][1]['complete']
report=m.analyze(record+b'X'+record+b'\0')
assert not any(w['complete'] for w in report['chain_walks'])
event=bytearray(156);event[12:16]=bytes.fromhex('886c8001');event[19:24]=bytes.fromhex('0010180001');event[25]=2;event[31]=52;event[47]=84
assert m.analyze(event)['canonical_events']==[dict(ethernet_offset=0,event=52,version=2,body_bytes=84)]
assert not m.analyze(event[:-1])['canonical_events']
print('PASS outer scanner: record chain, zero-only padding, embedded-header blob, invalid checksum, event bounds and absence of raw/string export')

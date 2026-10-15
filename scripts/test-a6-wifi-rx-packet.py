#!/usr/bin/env python3
"""Check private snapshot framing, bounds and position-free byte searches."""
import base64
import importlib.util
import os
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location('packet', Path(__file__).with_name('a6-capture-wifi-rx-packet.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
status = 'A6_WIFI_USB_BULK_RX_V1 enabled=1 attempted=1 submitted=1 usb_result=0 registered=1 deregistered=1 claimed=1 disconnected=1 release=0 tx=0 bytes=178'
data = bytes(range(178))
console = "echo P_BEGIN; base64; echo P_END\r\n" + status + '\r\nP_BEGIN\r\n' + base64.b64encode(data).decode() + '\r\nP_END\r\n'
assert m.parse_capture(console, 'P') == data
for bad in [console.replace('bytes=178', 'bytes=177'), console.replace('usb_result=0', 'usb_result=-110'), console.replace('release=0', 'release=-5'), console + 'P_END\n', console.replace('P_BEGIN\r\n', ''), console.replace(base64.b64encode(data).decode(), '!'), console.replace('bytes=178', 'bytes=2049')]:
    try:
        m.parse_capture(bad, 'P')
    except ValueError:
        pass
    else:
        raise AssertionError('accepted malformed or unverified snapshot')
probe = b'\xff' * 7 + b'\x88\x6c\x00\x10\x18\x80\x00abc'
analysis = m.analyze(probe)
assert analysis['broadcast_offsets'] == [0, 1]
assert analysis['ethertype_886c_offsets'] == [7]
assert analysis['broadcom_oui_offsets'] == [9]
assert analysis['frame_control_8000_offsets'] == [12]
assert analysis['printable_ascii_bytes'] == 4
assert m.analyze(b'')['printable_ascii_fraction'] == 0
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / 'private'
    m.private_write(p, data)
    assert p.read_bytes() == data and p.stat().st_mode & 0o777 == 0o600
    try:
        m.private_write(p, b'overwrite')
    except FileExistsError:
        pass
    else:
        raise AssertionError('overwrote evidence')
print('PASS private snapshot markers/status/length, overlapping signature offsets, ASCII fraction, mode0600 and exclusive writes')

loop = 'A6_WIFI_USB_LOOPBACK_V1 enabled=1 attempted=1 out=1 in=1 restore=0 before=0 after=0 ctl_tx=4 ctl_rx=4 bytes=184'
journal=len(data).to_bytes(2,'little')+(50).to_bytes(4,'little')+data
loop_console = console.replace(base64.b64encode(data).decode(),base64.b64encode(journal).decode()).replace('tx=0', 'tx=1').replace('\r\nP_BEGIN', '\r\n'+loop+'\r\nP_BEGIN')
assert m.parse_capture(loop_console, 'P', loopback=True) == journal
assert m.split_journal(journal)==[data]
for old,new in [('restore=0','restore=-5'),('in=1','in=17'),('bytes=184','bytes=0')]:
 try:m.parse_capture(loop_console.replace(old,new), 'P', loopback=True)
 except ValueError:pass
 else:raise AssertionError('unverified loopback snapshot accepted')
tx=m.loopback_tx();a=m.analyze_loopback(tx)
assert a['kind']==2 and a['checksum_valid'] and a['length_matches'] and a['payload_equal'] and a['whole_frame_equal']
for length in range(16):assert not m.analyze_loopback(tx[:length])['checksum_valid']
bad=bytearray(tx);bad[2]^=1;assert not m.analyze_loopback(bad)['checksum_valid']
assert m.analyze_loopback(tx+b'padding')['body_has_expected_prefix']
assert m.analyze_loopback(tx[:16]+b'prefix'+tx[16:])['body_has_expected_suffix']
assert not m.analyze_loopback(tx[:16]+b'status')['payload_equal']
print('PASS loopback private capture: restored ownership, report all kinds/lengths/checksums, exact/prefix/suffix and short-status comparisons')

for count in range(1,17):assert m.split_journal(journal*count)==[data]*count
for invalid in (journal*17,b'\x00',b'\x01\x08',b'\xb2\x00short'):
 try:m.split_journal(invalid)
 except ValueError:pass
 else:raise AssertionError('invalid journal accepted')
print('PASS private sixteen-packet timed journal bounds/counts/truncations and preservation')

bare=m.analyze_loopback(tx[16:]);assert not bare['header_present'] and bare['payload_equal']
assert bare['kind'] is None and bare['declared_bytes'] is None and bare['checksum_valid'] is None and bare['body_bytes']==64
print('PASS headerless BDC body comparison; absent USB fields reported as absent')

marker=m.loopback_tx()[38:]
odd=m.analyze_loopback(b'unknown-wrapper'+marker+b'trailer')
assert odd['pattern_offsets']==[15] and not odd['payload_equal']
print('PASS position-free distinctive pattern search without echo overclaim')

second=m.loopback_tx(2)
assert second != tx and len(second)==96 and second[38:80] == bytes(x ^ 255 for x in tx[38:])
for variant,frame in ((1,tx),(2,second)):
 a=m.analyze_loopback(b'\0'*176+frame+b'\0'*1600,variant)
 assert a['whole_tx_match_offsets']==[176] and a['payload_match_offsets_in_reply']==[192]
 assert a['tag_offsets']==[202] and a['pattern_offsets']==[214] and not a['payload_equal']
 assert not m.analyze_loopback(frame,3-variant)['payload_match_offsets_in_reply']
print('PASS two distinct payload variants and embedded full-frame offsets without framing overclaim')

bad_control=m.loopback_tx(3)
assert len(bad_control)==len(second) and sum(a!=b for a,b in zip(bad_control,second))==1
assert bad_control[2]==(second[2]^1) and bad_control[3:]==second[3:]
assert not m.analyze_loopback(bad_control,3)['checksum_valid']
assert m.analyze_loopback(bad_control,3)['whole_frame_equal']
assert m.analyze_loopback(second,2)['checksum_valid']
print('PASS negative control differs only by one checksum bit; exact content matching remains independent of header validation')

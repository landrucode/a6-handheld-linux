#!/usr/bin/env python3
"""Verify CIS framing and reject ambiguous/malformed stock product selections."""
import importlib.util
from pathlib import Path

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('selection',root/'scripts/verify-a6-wifi-otp-selection.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def cis(chip=b's=B3',rf=b'M=HEIN m=2.6 V=t'):
    payload=b'\x08\x00'+chip+b'\x00'+rf+b'\x00\x00\x00\xff'
    return bytes((0x15,len(payload)))+payload+b'\xff'
product={'HSICChipInfo':['s=B3'],'HSICRFHardwareInfo':['M=HEIN','V=t'],
         'vendor-id':'TDK','FilesDB':{'default':{'Firmware':'4334b1/centennial.trx','NVRAM':'4334b1/heineken-t-st.txt'}}}
metadata=[{'CFBundleIdentifier':'com.apple.driver.AppleBCMWLANBusInterfaceHSICShim',
           'IOKitPersonalities':{'4334':{'HSICProductInfo':{'Heineken - 4334B3 - TDK':product}}}}]
assert m.select(cis(),metadata)['vendor']=='TDK'
assert m.select(cis(rf=b'M=HEIN,m=2.6,V=t'),metadata)['vendor']=='TDK'
invalid=[b'',cis()[:-1],cis()+b'\x12',b'\x15\xff'+cis()[2:],cis()[:-1]+cis(),
         cis(chip=b's=B2'),cis(rf=b'M=HEIN V=u'),cis(rf=b'M=HEIN V=t V=u'),
         cis(rf=b'M=HEIN V=t V=t'),cis(rf=b'M=HEIN V=t bad'),cis(rf=b'M=HEIN V=t\x80')]
for data in invalid:
    try:m.select(data,metadata)
    except (ValueError,UnicodeDecodeError):pass
    else:raise AssertionError('malformed/mismatched CIS accepted')
ambiguous=[{'CFBundleIdentifier':metadata[0]['CFBundleIdentifier'],
           'IOKitPersonalities':{'4334':{'HSICProductInfo':{'Heineken - 4334B3 - TDK':product,'duplicate':product}}}}]
try:m.select(cis(),ambiguous)
except ValueError:pass
else:raise AssertionError('ambiguous stock product accepted')
print('CIS framing, unique stock product matching and malformed/ambiguous refusals passed')

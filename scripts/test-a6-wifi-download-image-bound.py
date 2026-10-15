#!/usr/bin/env python3
"""Execute actual wrapper bounds: unchanged legacy cap and gated 8KiB allowance."""
import os
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
s=(root/'scripts/build-a6-kernelcache.sh').read_text()
a=s.index('payload_file_offset = 0xff000')
b=s.index('\ndata[payload_file_offset:',a)
code=s[a:b]
environment={k:'1' for k in ('A6_USB_SHELL','A6_USB_NETWORK','A6_TOUCH_FRAME_CAPTURE',
                           'A6_RAM_ROOT','A6_TOUCH_RAM_ROOT_CANDIDATE','A6_SMP_SCHEDULING')}
def accepted(size,env):
    with patch.dict(os.environ,env,clear=True):
        try:exec(code,{'os':os,'text':(0x80001000,0x396000,0,0x396000,5,5),'payload':bytes(size),'entry_file_offset':0xb2084})
        except AssertionError:return False
    return True
assert accepted(0x28ffff,environment)
assert not accepted(0x290000,environment)
download=dict(environment,**{k:'1' for k in ('A6_WIFI_USB_DOWNLOAD','A6_WIFI_USB_OTP','A6_WIFI_USB_IDENTITY','A6_WIFI_EHCI_ENUM')})
assert accepted(2691332,download)
assert not accepted(0x292000,download)
assert not accepted(0x297000,download)
for feature in ('A6_WIFI_USB_OTP','A6_WIFI_USB_IDENTITY','A6_WIFI_EHCI_ENUM'):
    bad=dict(download);bad.pop(feature)
    assert not accepted(2691332,bad)
audio=dict(download,A6_AUDIO_FIFO_DISCOVER='1')
assert accepted(0x295fff,audio)
assert not accepted(0x296000,audio)
assert not accepted(0x297000,audio)
assert not accepted(0x292000,download)
print('Wrapper guard: legacy cap unchanged, actual payload accepted only with all gates, 8KiB/physical bounds enforced')

alsa=dict(audio,A6_AUDIO_ALSA='1',A6_AUDIO_TONE='1')
assert accepted(2740724,alsa)
assert accepted(0x2a4fff,alsa)
assert not accepted(0x2a5000,alsa)
assert not accepted(0x2a6001,alsa)
for flag in ('A6_AUDIO_FIFO_DISCOVER','A6_AUDIO_TONE'):
    bad=dict(alsa);bad.pop(flag)
    assert not accepted(2740724,bad)
print('ALSA payload stays wholly in TEXT; earlier source excludes entry; DATA crossing is rejected')

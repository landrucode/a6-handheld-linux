#!/usr/bin/env python3
"""Prepare a reviewable receive-only upstream brcmfmac patch; never apply it.

Pinned Linux remains untouched. The opt-in property is not in the boot DT.
Firmware loading, radio bring-up and bulk TX integration remain separate.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LINUX_HEAD = '587858367581b9c55c3690f4e63382ad622719d4'
USB = 'drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c'
HEADER = 'drivers/net/wireless/broadcom/brcm80211/brcmfmac/a6_hsic.h'


def render(source):
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('pinned source anchor mismatch')
        source = source.replace(old, new)
    replace('#include <linux/usb.h>', '#include <linux/usb.h>\n#include <linux/property.h>')
    replace('#include "bcdc.h"', '#include "bcdc.h"\n#include "a6_hsic.h"')
    replace('\t\tskb_put(skb, urb->actual_length);\n\t\tbrcmf_rx_frame', '''		skb_put(skb, urb->actual_length);
		/* Opt-in for a provisioned N42 host; never infer framing from VID alone. */
		if (device_property_read_bool(&devinfo->usbdev->dev,
					      "apple,hsic-usb-header")) {
			int offset;

			if (le16_to_cpu(devinfo->usbdev->descriptor.idVendor) != 0x0a5c ||
			    le16_to_cpu(devinfo->usbdev->descriptor.idProduct) != 0xbd1a)
				offset = -ENODEV;
			else
				offset = brcmf_a6_hsic_rx_offset(skb->data, skb->len);
			if (offset < 0) {
				brcmu_pkt_buf_free_skb(skb);
				brcmf_usb_rx_refill(devinfo, req);
				usb_mark_last_busy(urb->dev);
				return;
			}
			skb_pull(skb, offset);
		}
		brcmf_rx_frame''')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'build'):
        parser.error('review artifacts belong under build/')
    linux = ROOT/'.deps/linux'
    head = subprocess.check_output(['git','-C',str(linux),'rev-parse','HEAD'],text=True).strip()
    if head != LINUX_HEAD or subprocess.check_output(['git','-C',str(linux),'status','--porcelain'],text=True).strip():
        raise ValueError('pinned Linux checkout must be clean')
    original = (linux/USB).read_text()
    header = (ROOT/'kernel/platform/brcmfmac-a6-hsic.h').read_text()
    patch = ''.join(difflib.unified_diff(original.splitlines(True),render(original).splitlines(True),fromfile='a/'+USB,tofile='b/'+USB))
    patch += ''.join(difflib.unified_diff([],header.splitlines(True),fromfile='/dev/null',tofile='b/'+HEADER))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:
        f.write(patch)
    output.chmod(0o444)
    print(json.dumps({'patch':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'linux_head':head,'applied':False},indent=2))


if __name__ == '__main__':
    main()

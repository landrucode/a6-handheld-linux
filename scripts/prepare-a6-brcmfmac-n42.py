#!/usr/bin/env python3
"""Render native brcmfmac N42 transport in build/; no phone commands.

Uses proven external HOST_READY/download startup, then explicit runtime-ready
property for binding. Data TX stays blocked pending user's transmit approval.
"""
from pathlib import Path
import importlib.util,difflib,subprocess
ROOT=Path(__file__).resolve().parents[1]
USB='drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c'
def render(original):
 spec=importlib.util.spec_from_file_location('rx',ROOT/'scripts/prepare-a6-brcmfmac-hsic-patch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 s=m.render(original)
 def replace(old,new):
  nonlocal s
  if s.count(old)!=1:raise ValueError('pinned anchor mismatch: '+old[:70])
  s=s.replace(old,new)
 replace('#include "a6_hsic.h"', '''#include "a6_hsic.h"
static bool brcmf_usb_a6(struct usb_device *usb)
{
 return le16_to_cpu(usb->descriptor.idVendor) == 0x0a5c &&
        le16_to_cpu(usb->descriptor.idProduct) == 0xbd1a;
}
/* N42 UK mapping measured with this firmware; firmware selects its revision. */
static struct brcmfmac_pd_cc a6_country_codes = {
 .table_size = 1,
 .table = { { .iso3166 = "GB", .cc = "GB", .rev = -1 } }
};
static bool a6_allow_data_tx;
/* N42 runtime data TX is BDC-only; headered TX fails ARP/DHCP on hardware. */
static bool a6_tx_hsic_header;
module_param(a6_tx_hsic_header, bool, 0444);
MODULE_PARM_DESC(a6_tx_hsic_header, "N42 TX header mode; fixed at module load");
module_param(a6_allow_data_tx, bool, 0600);
MODULE_PARM_DESC(a6_allow_data_tx, "N42 data TX; enable only after transmit approval");''')
 replace('\tret = PTR_ERR_OR_ZERO(devinfo->settings);\n\tif (ret < 0)\n\t\tgoto fail;', '\tret = PTR_ERR_OR_ZERO(devinfo->settings);\n\tif (ret < 0)\n\t\tgoto fail;\n\tif (brcmf_usb_a6(devinfo->usbdev) && !devinfo->settings->country_codes)\n\t\tdevinfo->settings->country_codes = &a6_country_codes;')
 replace('BRCMF_FW_DEF(4373, "brcmfmac4373");','BRCMF_FW_DEF(4373, "brcmfmac4373");\nBRCMF_FW_DEF(4334A6, "brcmfmac4334-a6-usb");')
 replace('static const struct brcmf_firmware_mapping brcmf_usb_fwnames[] = {','static const struct brcmf_firmware_mapping brcmf_usb_fwnames[] = {\n\tBRCMF_FW_ENTRY(BRCM_CC_4334_CHIP_ID, 0xFFFFFFFF, 4334A6),')
 replace('\tuint rx_pipe, tx_pipe;', '\tuint rx_pipe, tx_pipe;\n\tu16 a6_tx_sequence;\n\tu8 a6_intr_ep, a6_intr_interval;\n\tu8 a6_intr_data[64] __aligned(64);\n\tstruct urb *a6_intr_urb;')
 replace('device_property_read_bool(&devinfo->usbdev->dev,\n\t\t\t\t\t      "apple,hsic-usb-header")','(brcmf_usb_a6(devinfo->usbdev) || device_property_read_bool(&devinfo->usbdev->dev,\n\t\t\t\t\t      "apple,hsic-usb-header"))')
 replace('\tdevinfo->ctl_read.bRequest = cmd;', '\tdevinfo->ctl_read.bRequest = cmd;\n\tdevinfo->ctl_read.wValue = cpu_to_le16(brcmf_usb_a6(devinfo->usbdev) ? 1 : 0);')
 replace('\tdevinfo->ctl_read.bRequest = 1;\n\n\tusb_fill_control_urb', '\tdevinfo->ctl_read.bRequest = 1;\n\tdevinfo->ctl_read.wValue = 0;\n\n\tusb_fill_control_urb')
 replace('brcmf_usb_dl_cmd(devinfo, DL_START, &state, sizeof(state))','brcmf_usb_dl_cmd(devinfo, brcmf_usb_a6(devinfo->usbdev) ? DL_GETSTATE : DL_START, &state, sizeof(state))')
 replace('\tif (chipid == BRCMF_POSTBOOT_ID) {', '''\tif (chipid == BRCMF_POSTBOOT_ID) {
        if (brcmf_usb_a6(devinfo->usbdev)) {
            devinfo->bus_pub.devid = BRCM_CC_4334_CHIP_ID;
            devinfo->bus_pub.chiprev = 3;
            devinfo->bus_pub.bus->chip = BRCM_CC_4334_CHIP_ID;
            devinfo->bus_pub.bus->chiprev = 3;
        }''')
 replace('static int brcmf_usb_up(struct device *dev)', '''static void brcmf_usb_a6_intr(struct urb *urb)
{
 struct brcmf_usbdev_info *d = urb->context;
 if (!urb->status && d->bus_pub.state == BRCMFMAC_USB_STATE_UP)
     usb_submit_urb(urb, GFP_ATOMIC);
}

static int brcmf_usb_up(struct device *dev)''')
 replace('\tbrcmf_usb_rx_fill_all(devinfo);\n\treturn 0;', '''    if (devinfo->a6_intr_urb) {
        usb_fill_int_urb(devinfo->a6_intr_urb, devinfo->usbdev,
            usb_rcvintpipe(devinfo->usbdev, devinfo->a6_intr_ep),
            devinfo->a6_intr_data, sizeof(devinfo->a6_intr_data),
            brcmf_usb_a6_intr, devinfo, devinfo->a6_intr_interval);
        if (usb_submit_urb(devinfo->a6_intr_urb, GFP_KERNEL))
            brcmf_err("N42 interrupt drain submission failed\\n");
    }
\tbrcmf_usb_rx_fill_all(devinfo);
\treturn 0;''')
 replace('\tif (devinfo->ctl_urb)\n\t\tusb_kill_urb', '\tif (devinfo->a6_intr_urb)\n\t\tusb_kill_urb(devinfo->a6_intr_urb);\n\tif (devinfo->ctl_urb)\n\t\tusb_kill_urb')
 replace('\tusb_free_urb(devinfo->ctl_urb);','\tusb_free_urb(devinfo->a6_intr_urb);\n\tusb_free_urb(devinfo->ctl_urb);')
 replace('\treturn &devinfo->bus_pub;', '''    if (devinfo->a6_intr_ep) {
        devinfo->a6_intr_urb = usb_alloc_urb(0, GFP_ATOMIC);
        if (!devinfo->a6_intr_urb) goto error;
    }
\treturn &devinfo->bus_pub;''')
 replace('\t\tif (!usb_endpoint_xfer_bulk(endpoint))\n\t\t\tcontinue;', '''        if (brcmf_usb_a6(usb) && usb_endpoint_is_int_in(endpoint)) {
            if (usb_endpoint_maxp(endpoint) > 64 || devinfo->a6_intr_ep) {
                ret = -ENODEV; goto fail;
            }
            devinfo->a6_intr_ep = endpoint_num;
            devinfo->a6_intr_interval = endpoint->bInterval;
        }
\t\tif (!usb_endpoint_xfer_bulk(endpoint))
\t\t\tcontinue;''')
 replace('\tbrcmf_dbg(USB, "Enter 0x%04x:0x%04x\\n", id->idVendor, id->idProduct);', '''    /* External proven startup owns HOST_READY and cold firmware execution. */
    if (brcmf_usb_a6(usb)) {
        if (!device_property_read_bool(&usb->dev, "apple,a6-runtime-ready"))
            return -EPROBE_DEFER;
        usb_disable_autosuspend(usb);
    }
\tbrcmf_dbg(USB, "Enter 0x%04x:0x%04x\\n", id->idVendor, id->idProduct);''')
 replace('static const struct usb_device_id brcmf_usb_devid_table[] = {','static const struct usb_device_id brcmf_usb_devid_table[] = {\n\tBRCMF_USB_DEVICE(0xbd1a),')
 # Transport framing implementation stays disabled by default for actual TX.
 replace('\tret = usb_autopm_get_interface(intf);\n\tif (ret)\n\t\tgoto out;\n\n\tbrcmf_dbg(USB, "Enter, skb=%p\\n", skb);', '''	if (brcmf_usb_a6(devinfo->usbdev) && !a6_allow_data_tx) {
		return -EACCES;
	}
\tret = usb_autopm_get_interface(intf);
\tif (ret)
\t\tgoto out;
\n\tbrcmf_dbg(USB, "Enter, skb=%p\\n", skb);''')
 replace('\treq->skb = skb;\n\treq->devinfo = devinfo;', '''    if (brcmf_usb_a6(devinfo->usbdev) && a6_tx_hsic_header) {
        u16 sequence;
        unsigned int payload;
        u8 *header;
        ret = skb_cow_head(skb, 16);
        if (!ret && (!skb->len || skb->len > 65519)) ret = -EMSGSIZE;
        if (ret) {
            brcmf_usb_enq(devinfo, &devinfo->tx_freeq, req, &devinfo->tx_freecount);
            goto fail;
        }
        spin_lock_irqsave(&devinfo->qlock, flags);
        sequence = devinfo->a6_tx_sequence++;
        spin_unlock_irqrestore(&devinfo->qlock, flags);
        payload = skb->len;
        header = skb_push(skb, 16);
        brcmf_a6_hsic_tx_header(header, payload, sequence);
    }
\treq->skb = skb;
\treq->devinfo = devinfo;''')
 replace('\t\treq->skb = NULL;\n\t\tbrcmf_usb_enq(devinfo, &devinfo->tx_freeq', '\t\treq->skb = NULL;\n        if (brcmf_usb_a6(devinfo->usbdev) && a6_tx_hsic_header) skb_pull(skb, 16);\n\t\tbrcmf_usb_enq(devinfo, &devinfo->tx_freeq')
 replace('\tbrcmf_proto_bcdc_txcomplete(devinfo->dev, req->skb, urb->status == 0);', '\tif (brcmf_usb_a6(devinfo->usbdev) && a6_tx_hsic_header) skb_pull(req->skb, 16);\n\tbrcmf_proto_bcdc_txcomplete(devinfo->dev, req->skb, urb->status == 0);')
 spec=importlib.util.spec_from_file_location('diag',ROOT/'scripts/prepare-a6-brcmfmac-diagnostics.py');diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
 return diag.render(s)
if __name__=='__main__':
 source=subprocess.check_output(['git','-C',str(ROOT/'.deps/linux'),'show','HEAD:'+USB],text=True)
 modified=render(source);out=ROOT/'build/brcmfmac-n42.patch';patch=''.join(difflib.unified_diff(source.splitlines(True),modified.splitlines(True),fromfile='a/'+USB,tofile='b/'+USB));header=USB.rsplit('/',1)[0]+'/a6_hsic.h';patch+=''.join(difflib.unified_diff([], (ROOT/'kernel/platform/brcmfmac-a6-hsic.h').read_text().splitlines(True),fromfile='/dev/null',tofile='b/'+header));out.write_text(patch)
 print('Native N42 transport patch rendered:',out.relative_to(ROOT))

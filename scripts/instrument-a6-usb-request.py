#!/usr/bin/env python3
"""Build-temporary USB telemetry; no controller writes or synthetic IRQs."""
from pathlib import Path
import sys
import os
repo, linux = map(Path, sys.argv[1:])
def edit(relative, pairs, prefix="", suffix=""):
    p = linux / relative
    s = p.read_text()
    for old, new in pairs:
        assert s.count(old) == 1, (relative, old)
        s = s.replace(old, new, 1)
    p.write_text(prefix + s + suffix)

decl = 'extern unsigned int a6_usb_diag[12];\n'
edit("drivers/phy/phy-apple-a6-usb.c", [
    ("static int a6_usb_power_on(struct phy *phy)", "static int a6_usb_power_on_impl(struct phy *phy)"),
    ("static int a6_usb_power_off(struct phy *phy)", """static int a6_usb_power_on(struct phy *phy)
{
    int ret;
    a6_usb_diag[2]++;
    ret = a6_usb_power_on_impl(phy);
    a6_usb_diag[3] = ret;
    return ret;
}

static int a6_usb_power_off(struct phy *phy)"""),
], decl)
edit("drivers/clocksource/timer-apple-a6.c", [
    ('    trace_row(0, "TIMER OBSERVE", 0);', '''    static bool reported;
    if (reported) return;
    reported = true;
    trace_row(0, "TIMER OBSERVE", 0);'''),
])
edit("drivers/usb/gadget/legacy/serial.c", [
    ("static int gs_bind(struct usb_composite_dev *cdev)", "static int gs_bind_impl(struct usb_composite_dev *cdev)"),
    ("static int gs_unbind(struct usb_composite_dev *cdev)", """static int gs_bind(struct usb_composite_dev *cdev)
{
    int ret;
    a6_usb_diag[4]++;
    ret = gs_bind_impl(cdev);
    a6_usb_diag[5] = ret;
    return ret;
}

static int gs_unbind(struct usb_composite_dev *cdev)"""),
], decl)
edit("drivers/usb/dwc2/gadget.c", [
    ('\t\t"ctrl Type=%02x, Req=%02x, V=%04x, I=%04x, L=%04x\\n",', '\t\t"ctrl Type=%02x, Req=%02x, V=%04x, I=%04x, L=%04x\\n",'),
    ('\tif (ctrl->wLength == 0) {', '''    a6_usb_diag[8]++;
    a6_usb_diag[9] = (ctrl->bRequestType << 24) | (ctrl->bRequest << 16) | le16_to_cpu(ctrl->wValue);
\tif (ctrl->wLength == 0) {'''),
    ('\tu32 gintmsk;\n\n\tif (!dwc2_is_device_mode(hsotg))', '\tu32 gintmsk;\n\n\ta6_usb_diag[7]++;\n\tif (!dwc2_is_device_mode(hsotg))'),
], decl)
edit("drivers/irqchip/irq-apple-a6-aic.c", [
    ('\t\ta6_trace_aic_last = event;', '\t\ta6_trace_aic_last = event;\n\t\tif (event == 0x0001000b) a6_usb_diag[6]++;'),
], decl, '''
u32 a6_usb_aic_read(u32 offset);
u32 a6_usb_aic_read(u32 offset)
{
    /* Never expose the destructive event/ack register. */
    if (!a6_aic_base || (offset != 0x4200 && offset != 0x4100 && offset != 0x302c))
        return ~0U;
    return readl(a6_aic_base + offset);
}
''')
pairs = [("static int dwc2_driver_probe(struct platform_device *dev)",
          "static int dwc2_driver_probe_impl(struct platform_device *dev)")]
for stage, call in enumerate(["dwc2_lowlevel_hw_init", "dwc2_lowlevel_hw_enable", "dwc2_get_dr_mode", "dwc2_check_core_version", "dwc2_core_reset", "dwc2_get_hwparams", "dwc2_init_params", "dwc2_drd_init", "dwc2_gadget_init"], 1):
    old = f"retval = {call}(hsotg"
    pairs.append((old, f"a6_usb_diag[0] = {stage};\n\t" + old))
pairs.append(("static int __maybe_unused dwc2_suspend(struct device *dev)",
              (repo / "kernel/platform/a6-usb-request-report.inc").read_text() +
              "\nstatic int __maybe_unused dwc2_suspend(struct device *dev)"))
edit("drivers/usb/dwc2/platform.c", pairs, decl + '#include <linux/workqueue.h>\n')
if os.environ.get("A6_USB_SYNC_TRACE") == "1":
    edit("drivers/usb/dwc2/platform.c", [
        ("static DECLARE_DELAYED_WORK(a6_usb_report_job, a6_usb_report_work);", ""),
        ("    if (a6_report_count < 60) schedule_delayed_work(&a6_usb_report_job, HZ);", ""),
        ("    schedule_delayed_work(&a6_usb_report_job, 2 * HZ);", ""),
    ], suffix='''
void a6_usb_report_sync(void);
void a6_usb_report_sync(void)
{
    usb_report_row(0, "USB SNAPSHOT ENTER", 0);
    a6_usb_report_work(NULL);
}
''')
    edit("init/main.c", [
        ("\t\ta6_kinit_exec();", "\t\ta6_kinit_exec();\n\t\ta6_usb_report_sync();"),
    ], prefix="extern void a6_usb_report_sync(void);\n")
if os.environ.get("A6_USB_WAIT_TRACE") == "1":
    assert os.environ.get("A6_USB_SYNC_TRACE") == "1"
    edit("drivers/usb/dwc2/platform.c", [
        ('''void a6_usb_report_sync(void)
{
    usb_report_row(0, "USB SNAPSHOT ENTER", 0);
    a6_usb_report_work(NULL);
}''', (repo / "kernel/platform/a6-usb-wait-observe.inc").read_text()),
    ])

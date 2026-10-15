#!/usr/bin/env python3
"""Install narrow N42 quirks into the pinned EHCI tree; no device access."""
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (str(path), old)
    path.write_text(text.replace(old, new))

header = root / 'drivers/usb/host/ehci.h'
replace(header, '\t/* platform-specific data -- must come last */',
        '\tbool a6_wlan_only; /* Opt-in N42 trial: expose only root port 4. */\n'
        '\tbool a6_irq_fault, a6_forcing_resume;\n\tu32 a6_irq_status, a6_irq_restarts, a6_port_traces, a6_inactive_resumes;\n\n'
        '\t/* platform-specific data -- must come last */')
guard = '''
static inline bool a6_ehci_hidden_port(const struct ehci_hcd *ehci,
                                      __u32 __iomem *reg)
{
    unsigned long address = (unsigned long)reg;
    unsigned long first;
    if (!ehci->a6_wlan_only || !ehci->regs)
        return false;
    first = (unsigned long)&ehci->regs->port_status[0];
    return address >= first && address < first + 3 * sizeof(u32);
}

'''
replace(header, 'static inline unsigned int ehci_readl(', guard + 'static inline unsigned int ehci_readl(')
replace(header, '\t\t__u32 __iomem *regs)\n{\n#ifdef CONFIG_USB_EHCI_BIG_ENDIAN_MMIO',
        '\t\t__u32 __iomem *regs)\n{\n'
        '\tif (a6_ehci_hidden_port(ehci, regs))\n\t\treturn 0;\n'
        '#ifdef CONFIG_USB_EHCI_BIG_ENDIAN_MMIO')
replace(header, '\t\tconst unsigned int val, __u32 __iomem *regs)\n{\n',
        '\t\tconst unsigned int val, __u32 __iomem *regs)\n{\n'
        '\tif (a6_ehci_hidden_port(ehci, regs))\n\t\treturn;\n')
hub = root / 'drivers/usb/host/ehci-hub.c'
# Adapt the HSIC reset-completion quirk from Project Cascadia (GPL-2.0),
# 00303679c33afcf2e59b26671b584a69a9718789, patches/tree/0001-cascadia.patch.
replace(hub, '\t\t\t\t\tPORT_RESET, 0, 1000);',
        '\t\t\t\t\tPORT_RESET, 0,\n'
        '\t\t\t\t\t(ehci->a6_wlan_only && wIndex == 3) ? 20000 : 1000);')
# N42 ADT hsic-port-errata: force resume before each WLAN port reset.
replace(hub, '\t\tcase USB_PORT_FEAT_RESET:\n',
        '\t\tcase USB_PORT_FEAT_RESET:\n'
        '\t\t\tif (ehci->a6_wlan_only && wIndex == 3) {\n'
        '\t\t\t\t/* Explicit reset supersedes a pending remote resume. */\n'
        '\t\t\t\tif (test_and_clear_bit(wIndex, &ehci->resuming_ports)) {\n'
        '\t\t\t\t\tclear_bit(wIndex, &ehci->suspended_ports);\n'
        '\t\t\t\t\tehci->reset_done[wIndex] = 0;\n'
        '\t\t\t\t\tusb_hcd_end_port_resume(&hcd->self, wIndex);\n'
        '\t\t\t\t}\n'
        '\t\t\t\tehci->a6_forcing_resume = true;\n'
        '\t\t\t\tehci_writel(ehci, (temp & ~PORT_RWC_BITS) | PORT_RESUME, status_reg);\n'
        '\t\t\t\tspin_unlock_irqrestore(&ehci->lock, flags);\n'
        '\t\t\t\tmsleep(20);\n'
        '\t\t\t\tspin_lock_irqsave(&ehci->lock, flags);\n'
        '\t\t\t\ttemp = ehci_readl(ehci, status_reg) & ~(PORT_RWC_BITS | PORT_RESUME);\n'
        '\t\t\t\tehci_writel(ehci, temp, status_reg);\n'
        '\t\t\t\tehci->a6_forcing_resume = false;\n'
        '\t\t\t}\n')

# Polling during the unlocked forced pulse must not start remote-wake state.
replace(hub, '\t\t\tif (temp & PORT_RESUME) {\n',
        '\t\t\tif ((temp & PORT_RESUME) && !(ehci->a6_wlan_only &&\n'
        '\t\t\t    wIndex == 3 && ehci->a6_forcing_resume)) {\n')
# N42 observation: RESUME remains asserted on active, nonsuspended HSIC port4.
# Do not turn that indication into remote-wakeup state or report suspension.
# Preserve genuine suspended/in-progress resumes and the raw snapshot below.
replace(hub, '\t\twIndex--;\n\t\tstatus = 0;\n\t\ttemp = ehci_readl(ehci, status_reg);\n',
        '\t\twIndex--;\n\t\tstatus = 0;\n\t\ttemp = ehci_readl(ehci, status_reg);\n'
        '\t\t/* A6 inactive resume indication: software view only. */\n'
        '\t\tif (ehci->a6_wlan_only && wIndex == 3 &&\n'
        '\t\t    (temp & PORT_RESUME) && !(temp & PORT_SUSPEND) &&\n'
        '\t\t    !test_bit(wIndex, &ehci->suspended_ports) &&\n'
        '\t\t    !test_bit(wIndex, &ehci->resuming_ports) &&\n'
        '\t\t    !ehci->a6_forcing_resume) {\n'
        '\t\t\tehci->a6_inactive_resumes++;\n'
        '\t\t\ttemp &= ~PORT_RESUME;\n'
        '\t\t}\n')

# Reset completion rereads PORTSC; normalize that refreshed software view too.
replace(hub, '\t\t/* maybe the port was unsuspended without our knowledge */',
        '\t\t/* A6 inactive resume indication: software view only. */\n'
        '\t\tif (ehci->a6_wlan_only && wIndex == 3 &&\n'
        '\t\t    (temp & PORT_RESUME) && !(temp & PORT_SUSPEND) &&\n'
        '\t\t    !test_bit(wIndex, &ehci->suspended_ports) &&\n'
        '\t\t    !test_bit(wIndex, &ehci->resuming_ports) &&\n'
        '\t\t    !ehci->a6_forcing_resume) {\n'
        '\t\t\tehci->a6_inactive_resumes++;\n'
        '\t\t\ttemp &= ~PORT_RESUME;\n'
        '\t\t}\n'
        '\t\t/* maybe the port was unsuspended without our knowledge */')

# Read-only snapshots on the trial port, bounded across all hub operations.
replace(hub, 'error_exit:\n\tspin_unlock_irqrestore (&ehci->lock, flags);',
        'error_exit:\n'
        '\tif (ehci->a6_wlan_only && status_reg == &ehci->regs->port_status[3] &&\n'
        '\t    ehci->a6_port_traces < 24) {\n'
        '\t\tehci->a6_port_traces++;\n'
        '\t\tehci_info(ehci, "A6_HSIC_PORT_V1 req=%04x feature=%u raw=%08x ret=%d forcing=%u resuming=%u reset_due=%lu\\n",\n'
        '\t\t\t  typeReq, wValue, ehci_readl(ehci, status_reg), retval,\n'
        '\t\t\t  ehci->a6_forcing_resume,\n'
        '\t\t\t  !!test_bit(3, &ehci->resuming_ports), ehci->reset_done[3]);\n'
        '\t}\n'
        '\tspin_unlock_irqrestore (&ehci->lock, flags);')

# Bound a hardware status that reasserts while IRQs are disabled. Only the
# explicit N42 trial takes this branch; reuse normal controller-death cleanup.
hcd = root / 'drivers/usb/host/ehci-hcd.c'
replace(hcd, '\tint\t\t\tbh;\n',
        '\tint\t\t\tbh;\n\tunsigned int a6_restarts = 0;\n')
replace(hcd, 'restart:\n', 'restart:\n'
        '\tif (ehci->a6_wlan_only) {\n'
        '\t\tehci->a6_irq_status = current_status;\n'
        '\t\tif (++a6_restarts > 64) {\n'
        '\t\t\tehci->a6_irq_fault = true;\n'
        '\t\t\tehci_err(ehci, "A6 IRQ restart bound: status=%08x loops=%u\\n", current_status, a6_restarts);\n'
        '\t\t\tgoto dead;\n'
        '\t\t}\n'
        '\t\tehci->a6_irq_restarts++;\n'
        '\t}\n')

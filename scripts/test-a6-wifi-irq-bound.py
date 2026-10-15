#!/usr/bin/env python3
"""Exercise the real opt-in IRQ guard from a patch of pristine pinned sources."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    host = temp/'drivers/usb/host'
    host.mkdir(parents=True)
    for name in ('ehci.h', 'ehci-hub.c', 'ehci-hcd.c'):
        blob = subprocess.check_output(['git','-C',str(root/'.deps/linux'),
                                       'show','HEAD:drivers/usb/host/'+name])
        (host/name).write_bytes(blob)
    subprocess.run(['python3',str(root/'scripts/patch-a6-ehci-trial.py'),str(temp)],check=True)
    patched = (host/'ehci-hcd.c').read_text()
    begin = patched.index('restart:\n') + len('restart:\n')
    end = patched.index('\n\t/* e.g. cardbus physical eject */',begin)
    guard = patched[begin:end]
    harness = '''#include <stdbool.h>
#include <stdint.h>
#include <assert.h>
#define ehci_err(...) ((void)0)
struct controller { bool a6_wlan_only, a6_irq_fault; uint32_t a6_irq_status, a6_irq_restarts; };
static int run(struct controller *ehci, unsigned int passes) {
unsigned int a6_restarts=0; uint32_t current_status=4;
for(unsigned int n=0;n<passes;n++) {
''' + guard + '''
} return 0;
dead: return 1;
}
int main(void) {
struct controller active={.a6_wlan_only=true};
assert(run(&active,64)==0 && !active.a6_irq_fault && active.a6_irq_restarts==64);
active.a6_irq_restarts=0;
assert(run(&active,100000)==1 && active.a6_irq_fault && active.a6_irq_restarts==64 && active.a6_irq_status==4);
struct controller ordinary={0};
assert(run(&ordinary,100000)==0 && !ordinary.a6_irq_fault && ordinary.a6_irq_restarts==0);
}'''
    (temp/'guard.c').write_text(harness)
    subprocess.run(['cc','-std=c99',str(temp/'guard.c'),'-o',str(temp/'guard')],check=True)
    subprocess.run([str(temp/'guard')],check=True)
    assert 'goto dead;' in guard
    assert 'ehci_writel(ehci, 0, &ehci->regs->intr_enable);' in patched
print('Opt-in IRQ restart bound and ordinary-controller control passed')

#!/usr/bin/env python3
"""Instrument build-temporary kernel sources; caller owns restoration.

This is an opt-in generation step, not a patch to the USB state machine.
Every replacement is guarded against source drift.
"""
from pathlib import Path
import os
import re
import sys
import subprocess

repo, linux = map(Path, sys.argv[1:])
phy_trace = os.environ.get("A6_USB_PHY_TRACE") == "1"

def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"ambiguous diagnostic anchor: {old!r}")
    return text.replace(old, new, 1)

wrapper = r"""
.macro a6_boot_hook name, stage
.global \name
.type \name, %function
.thumb_func
\name:
    push {r0-r12, lr}
    mrs r12, cpsr
    push {r11, r12}
    cpsid if
    mov r0, #\stage
    bl a6_boot_draw
    pop {r11, r12}
    msr cpsr_cxsf, r12
    pop {r0-r12, pc}
.endm
"""
head = linux / "arch/arm/kernel/head.S"
text = head.read_text()
hooks = {
    "a6_stage_stack": 1, "a6_stage_archin": 2,
    "a6_arch_proc": 3, "a6_arch_fdt": 4, "a6_arch_memblock": 5,
    "a6_arch_pagingin": 6, "a6_page_prepare": 7, "a6_arch_paging": 8,
    "a6_stage_irqon": 9, "a6_stage_rest": 10, "a6_kinit_enter": 11,
    "a6_kinit_basic": 19, "a6_kinit_exec": 20,
    "a6_userspace_syscall": 21, "a6_fault_undef": 22,
    "a6_fault_memory": 23,
}
for name, stage in hooks.items():
    text, n = re.subn(r"^a6_(?:c|visible|quick)_stage " + name + r",[^\n]*$",
                      f"a6_boot_hook {name}, {stage}", text, flags=re.M)
    if n != 1:
        raise RuntimeError(f"missing hook {name}")
# Do not erase the early boot ledger at CPU-setup return. Keep its register
# changes and loop bounds; omit only the framebuffer stores.
text = replace(text, "19:\tstr\tr10, [r6], #4", "19:\tadd\tr6, r6, #4")
text = replace(text, "\tstr\tr4, [r3, #8]\n\tpop\t{r0-r12, pc}",
               "\tstr\tr4, [r3, #8]\n\tbl a6_diag_mmu\n\tpop\t{r0-r12, pc}")
text = wrapper + text
text += '\n.pushsection .text, "ax", %progbits\n.thumb\n'
for name, stage in {"mmu": 0, "dwc_probe": 12, "phy_probe": 13,
                    "phy_power": 14, "phy_ready": 15, "params": 16,
                    "udc": 17, "serial": 18}.items():
    text += f"a6_boot_hook a6_diag_{name}, {stage}\n"
text += ".popsection\n"
renderer = (repo / "boot/arm/linux-boot-status.S").read_text()
if phy_trace:
    phases = ["14 PHY SLEEP 10MS", "14 PHY SLEEP RETURNED",
              "14 PHY GATE 0 WAIT", "14 PHY GATE 1 WAIT", "14 PHY GATE 2 WAIT",
              "14 PHY GATES READY", "14 PHY UDELAY 100US", "14 PHY TUNING WRITES",
              "14 PHY UDELAY 10US", "14 PHY RESET 20US", "14 PHY SLEEP 1MS",
              "14 PHY ATTACH WRITE", "14 PHY READBACKS", "14 PHY RETURN ERROR"]
    text += '\n.pushsection .text, "ax", %progbits\n.thumb\n'
    for i in range(len(phases)):
        text += f"a6_boot_hook a6_diag_phy_p{i}, {32+i}\n"
    text += ".popsection\n"
    renderer = replace(renderer, "    ldr r1, =a6_boot_labels\n    ldr r7, [r1, r0, lsl #2]\n", "")
    renderer = replace(renderer, "a6_boot_draw:\n", """a6_boot_draw:
    cmp r0, #32
    blo 10f
    sub r0, r0, #32
    cmp r0, #14
    bhs 9f
    ldr r1, =a6_phy_labels
    ldr r7, [r1, r0, lsl #2]
    mov r0, #14
    b 11f
10:
""")
    renderer = replace(renderer, "    str r2, [r1]\n", """    str r2, [r1]
    ldr r1, =a6_boot_labels
    ldr r7, [r1, r0, lsl #2]
11:
""")
    data = "a6_phy_labels:\n    .word " + ",".join(f"a6_phy_label_{i}" for i in range(14)) + "\n"
    for i, phase in enumerate(phases):
        assert len(phase) <= 25
        data += f'a6_phy_label_{i}: .asciz "{phase:25s}"\n'
    renderer = replace(renderer, "a6_boot_font:\n", data + ".balign 4\na6_boot_font:\n")
text += renderer
text += f'\n.incbin "{repo / "kernel/font8x8.bin"}"\n.popsection\n'
head.write_text(text)

# Larger six early milestone blocks: 64x48 pixels, 80px spacing.
for path in [head, linux / "arch/arm/boot/compressed/head.S"]:
    text = path.read_text()
    def enlarge(m):
        return (m.group().replace("#40", "#80").replace("#32", "#64")
                .replace("#8\n", "#48\n"))
    text, n = re.subn(r"\.macro a6_ledger_mark[^\n]*\n.*?\.endm", enlarge,
                      text, flags=re.S)
    if n != 2:
        raise RuntimeError(f"unexpected ledger macro count {path}: {n}")
    path.write_text(text)

def instrument(relative, declarations, edits):
    p = linux / relative
    text = p.read_text()
    for old, new in edits:
        text = replace(text, old, new)
    p.write_text(declarations + text)

instrument("drivers/phy/phy-apple-a6-usb.c",
           "extern void a6_diag_phy_probe(void);\nextern void a6_diag_phy_power(void);\nextern void a6_diag_phy_ready(void);\n", [
    ("\tmsleep(10);", "\ta6_diag_phy_power();\n\tmsleep(10);"),
    ('\tdev_info(&phy->dev, "A6 USB PHY ready:', '\ta6_diag_phy_ready();\n\tdev_info(&phy->dev, "A6 USB PHY ready:'),
    ("\ta = devm_kzalloc", "\ta6_diag_phy_probe();\n\ta = devm_kzalloc"),
])
if phy_trace:
    instrument("drivers/phy/phy-apple-a6-usb.c",
               "".join(f"extern void a6_diag_phy_p{i}(void);\n" for i in range(14)), [
        ("\tmsleep(10);", "\ta6_diag_phy_p0();\n\tmsleep(10);\n\ta6_diag_phy_p1();"),
        ("\tfor (i = 0; i < ARRAY_SIZE(gates); i++) {",
         "\tfor (i = 0; i < ARRAY_SIZE(gates); i++) {\n\t\tif (i == 0) a6_diag_phy_p2();\n\t\telse if (i == 1) a6_diag_phy_p3();\n\t\telse a6_diag_phy_p4();"),
        ("\t\tif (ret)\n\t\t\treturn ret;", "\t\tif (ret) {\n\t\t\ta6_diag_phy_p13();\n\t\t\treturn ret;\n\t\t}"),
        ("\t/* Shared DWC2 clock-stop", "\ta6_diag_phy_p5();\n\t/* Shared DWC2 clock-stop"),
        ("\tudelay(100);", "\ta6_diag_phy_p6();\n\tudelay(100);\n\ta6_diag_phy_p7();"),
        ("\tudelay(10);", "\ta6_diag_phy_p8();\n\tudelay(10);"),
        ("\tudelay(20);", "\ta6_diag_phy_p9();\n\tudelay(20);"),
        ("\tusleep_range(1000, 2000);", "\ta6_diag_phy_p10();\n\tusleep_range(1000, 2000);\n\ta6_diag_phy_p11();"),
        ("\tif (readl(a->phy) != 6", "\ta6_diag_phy_p12();\n\tif (readl(a->phy) != 6"),
        ("\t    readl(a->phy + 0x1c) != 6)\n\t\treturn -EIO;",
         "\t    readl(a->phy + 0x1c) != 6) {\n\t\ta6_diag_phy_p13();\n\t\treturn -EIO;\n\t}"),
    ])
instrument("drivers/usb/dwc2/params.c", "extern void a6_diag_params(void);\n", [
    ("\tp->g_dma = false;\n\tp->g_dma_desc = false;", "\ta6_diag_params();\n\tp->g_dma = false;\n\tp->g_dma_desc = false;"),
])
instrument("drivers/usb/dwc2/platform.c",
           "extern void a6_diag_dwc_probe(void);\nextern void a6_diag_udc(void);\n", [
    ("\thsotg = devm_kzalloc", "\ta6_diag_dwc_probe();\n\thsotg = devm_kzalloc"),
    ("#endif /* CONFIG_USB_DWC2_PERIPHERAL || CONFIG_USB_DWC2_DUAL_ROLE */\n\treturn 0;",
     "#endif /* CONFIG_USB_DWC2_PERIPHERAL || CONFIG_USB_DWC2_DUAL_ROLE */\n\ta6_diag_udc();\n\treturn 0;"),
])
instrument("drivers/usb/gadget/legacy/serial.c", "extern void a6_diag_serial(void);\n", [
    ("\t/* register our configuration */", "\ta6_diag_serial();\n\t/* register our configuration */"),
])
if os.environ.get("A6_TIMER_TRACE") == "1":
    assert phy_trace
    subprocess.run([sys.executable, str(repo / "scripts/instrument-a6-timer-trace.py"),
                    str(repo), str(linux)], check=True)
if os.environ.get("A6_USB_REQUEST_TRACE") == "1":
    subprocess.run([sys.executable, str(repo / "scripts/instrument-a6-usb-request.py"),
                    str(repo), str(linux)], check=True)
if os.environ.get("A6_EXEC_TRACE") == "1":
    subprocess.run([sys.executable, str(repo / "scripts/instrument-a6-exec-trace.py"),
                    str(repo), str(linux)], check=True)
if os.environ.get("A6_EXEC_PREP_TRACE") == "1":
    subprocess.run([sys.executable, str(repo / "scripts/instrument-a6-exec-prep.py"),
                    str(repo), str(linux)], check=True)
if os.environ.get("A6_SHELL_EXEC_TRACE") == "1":
    subprocess.run([sys.executable, str(repo / "scripts/instrument-a6-shell-exec.py"),
                    str(repo), str(linux)], check=True)

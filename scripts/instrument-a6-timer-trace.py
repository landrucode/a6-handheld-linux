#!/usr/bin/env python3
"""Temporary, read-only timer observation; never replaces the PHY sleep."""
from pathlib import Path
import sys
import os

repo, linux = map(Path, sys.argv[1:])

def edit(relative, pairs, suffix=""):
    p = linux / relative
    s = p.read_text()
    for old, new in pairs:
        assert s.count(old) == 1, (relative, old)
        s = s.replace(old, new, 1)
    p.write_text(s + suffix)

edit("arch/arm/kernel/head.S", [
    ("    mov r0, #\\stage", "    .if \\stage == 255\n    add r0, r0, #64\n    .else\n    mov r0, #\\stage\n    .endif"),
    ("a6_boot_draw:\n", """a6_boot_draw:
    cmp r0, #64
    blo 12f
    sub r0, r0, #64
    cmp r0, #24
    bhs 9f
    mov r7, r1
    b 11f
12:
"""),
], '\n.pushsection .text, "ax", %progbits\n.thumb\na6_boot_hook a6_diag_timer_row, 255\n.popsection\n')

edit("drivers/irqchip/irq-apple-a6-aic.c", [
    ("static struct irq_domain *a6_aic_domain;", """static struct irq_domain *a6_aic_domain;
u32 a6_trace_aic_count, a6_trace_aic_last, a6_trace_aic_info;
u32 a6_trace_aic_clock(void);
u32 a6_trace_aic_clock(void)
{
    return a6_aic_base ? readl(a6_aic_base + 0x20) : 0;
}"""),
    ("\t\tif (AIC_EVENT_TYPE(event)", "\t\ta6_trace_aic_count++;\n\t\ta6_trace_aic_last = event;\n\t\tif (AIC_EVENT_TYPE(event)"),
    ("\tif (!nr_irqs ||", "\ta6_trace_aic_info = nr_irqs;\n\tif (!nr_irqs ||"),
])

edit("drivers/clocksource/timer-apple-a6.c", [
    ("static u32 a6_counter_rate;", """static u32 a6_counter_rate;
static u32 trace_stage, trace_error, trace_freq, trace_programs, trace_delta;
static u32 trace_irqs;
"""),
    ("\ta6_cntv_tval_write(delta);", "\ttrace_programs++;\n\ttrace_delta = delta;\n\ta6_cntv_tval_write(delta);"),
    ("\tif (++irq_count", "\ttrace_irqs++;\n\tif (++irq_count"),
    ('\tasm volatile("mrc p15, 0, %0, c14, c0, 0" : "=r" (cntfrq));', '\ttrace_stage = 1;\n\tasm volatile("mrc p15, 0, %0, c14, c0, 0" : "=r" (cntfrq));\n\ttrace_freq = cntfrq;'),
    ("\tif (!a6_counter_rate)\n\t\treturn -EINVAL;", "\tif (!a6_counter_rate) { trace_error = -EINVAL; return -EINVAL; }\n\ttrace_stage = 2;"),
    ("\tif (!spins)\n\t\treturn -ENODEV;", "\tif (!spins) { trace_error = -ENODEV; return -ENODEV; }\n\ttrace_stage = 3;"),
    ("\tif (!irq)\n\t\treturn -EINVAL;", "\tif (!irq) { trace_error = -EINVAL; return -EINVAL; }\n\ttrace_stage = 4;"),
    ("\tif (ret)\n\t\treturn ret;", "\tif (ret) { trace_error = ret; return ret; }\n\ttrace_stage = 5;"),
    ("\t\tclocksource_unregister", "\t\ttrace_error = ret;\n\t\tclocksource_unregister"),
    ("\tclockevents_config_and_register", "\ttrace_stage = 6;\n\tclockevents_config_and_register"),
    ('\tpr_info("A6 timer:', '\ttrace_stage = 7;\n\tpr_info("A6 timer:'),
], (repo / "kernel/platform/a6-timer-observe.inc").read_text())

edit("drivers/phy/phy-apple-a6-usb.c", [
    ("\tmsleep(10);", "\ta6_timer_observe();\n\tmsleep(10);"),
    ("extern void a6_diag_phy_p0(void);", "extern void a6_timer_observe(void);\nextern void a6_diag_phy_p0(void);"),
])

if os.environ.get("A6_TIMER_LINE_TRACE") == "1":
    assert os.environ.get("A6_AIC_ROUTE_TRACE") != "1"
    edit("drivers/irqchip/irq-apple-a6-aic.c", [],
         (repo / "kernel/platform/a6-timer-line-observe.inc").read_text())
    edit("drivers/phy/phy-apple-a6-usb.c", [
        ("extern void a6_timer_observe(void);", "extern void a6_line_observe(void);"),
        ("\ta6_timer_observe();", "\ta6_line_observe();"),
    ])

if os.environ.get("A6_AIC_ROUTE_TRACE") == "1":
    edit("drivers/irqchip/irq-apple-a6-aic.c", [
        ("static struct irq_domain *a6_aic_domain;", """static struct irq_domain *a6_aic_domain;
static u32 route_entries, route_delivered;
static bool route_active;
"""),
        ("\twhile ((event = readl(a6_aic_base + AIC_EVENT))) {",
         "\troute_entries++;\n\twhile ((event = readl(a6_aic_base + AIC_EVENT))) {"),
        ("\t\ta6_trace_aic_last = event;", """\t\ta6_trace_aic_last = event;
        if (READ_ONCE(route_active) && event == 0x000100a3) {
            /* Synthetic source: clear our software latch, leave auto-masked
             * until observer cleanup, and do NOT advance Linux's tick. */
            writel(BIT(3), a6_aic_base + AIC_SW_CLR + 20);
            route_delivered++;
            continue;
        }"""),
    ], (repo / "kernel/platform/a6-aic-route-observe.inc").read_text())
    edit("drivers/phy/phy-apple-a6-usb.c", [
        ("extern void a6_timer_observe(void);", "extern void a6_route_observe(void);"),
        ("\ta6_timer_observe();", "\ta6_route_observe();"),
    ])

#!/usr/bin/env python3
"""Install the opt-in N42 Linux bridge into caller-stashed kernel sources."""
import sys
import os
from pathlib import Path

repo, linux, output = map(Path, sys.argv[1:])


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"expected one bridge anchor: {old!r}")
    return text.replace(old, new)


head_path = linux / "arch/arm/kernel/head.S"
head = head_path.read_text()
head = replace_once(head, "\tadr_l\tr3, secondary_data\n",
                    "\tadr_l\tr3, a6_smp_secondary_data\n")
head = replace_once(head, "\tadr_l\tr7, secondary_data + 12\t\t@ get secondary_data.stack\n",
                    "\tadr_l\tr7, a6_smp_secondary_data + 12\t\t@ get secondary_data.stack\n")
smp_path = linux / "arch/arm/kernel/smp.c"
smp = smp_path.read_text()
smp = replace_once(smp, "struct secondary_data secondary_data;",
                   "struct secondary_data secondary_data;\n"
                   "extern void a6_smp_secondary_checkpoint(unsigned int cpu);")
smp = replace_once(smp, "\tnotify_cpu_starting(cpu);\n",
                   "\ta6_smp_secondary_checkpoint(cpu);\n\tnotify_cpu_starting(cpu);\n")
cpuhp_path = linux / "include/linux/cpuhotplug.h"
cpuhp = cpuhp_path.read_text()
cpuhp = replace_once(cpuhp, "\tCPUHP_AP_ARM_ARCH_TIMER_STARTING,\n",
                    "\tCPUHP_AP_ARM_ARCH_TIMER_STARTING,\n"
                    "\tCPUHP_AP_APPLE_A6_TIMER_STARTING,\n")
aic_path = linux / "drivers/irqchip/irq-apple-a6-aic.c"
aic = aic_path.read_text()
affinity = """
/* First SMP profile: only the CPU1 virtual-timer line may route to CPU1. */
void a6_smp_aic_timer_snapshot(u32 *hw, u32 *mask, u32 *target);
void a6_smp_aic_timer_snapshot(u32 *hw, u32 *mask, u32 *target)
{
    unsigned int bank;
    for (bank = 0; bank < 6; bank++) {
        hw[bank] = readl(a6_aic_base + 0x4200 + bank * 4);
        mask[bank] = readl(a6_aic_base + AIC_MASK_SET + bank * 4);
    }
    target[0] = readl(a6_aic_base + AIC_TARGET_CPU + 0xa2 * 4);
    target[1] = readl(a6_aic_base + AIC_TARGET_CPU + 0xa5 * 4);
    target[2] = readl(a6_aic_base + AIC_TARGET_CPU + 0xa6 * 4);
}

static int a6_smp_aic_set_affinity(struct irq_data *d,
                                 const struct cpumask *mask, bool force)
{
    unsigned int cpu = force ? cpumask_first(mask) :
                              cpumask_any_and(mask, cpu_online_mask);
    if (cpu >= nr_cpu_ids || cpu > 1 || (cpu == 1 && d->hwirq != 0xa5))
        return -EINVAL;
    writel(BIT(cpu), a6_aic_base + AIC_TARGET_CPU + d->hwirq * 4);
    if (readl(a6_aic_base + AIC_TARGET_CPU + d->hwirq * 4) != BIT(cpu))
        return -EIO;
    return IRQ_SET_MASK_OK;
}

"""
aic = replace_once(aic, "static struct irq_chip a6_aic_chip = {",
                   affinity + "static struct irq_chip a6_aic_chip = {")
aic = replace_once(aic, "\t.irq_eoi = a6_aic_eoi,",
                   "\t.irq_eoi = a6_aic_eoi,\n"
                   "\t.irq_set_affinity = a6_smp_aic_set_affinity,")
timer_path = linux / "drivers/clocksource/timer-apple-a6.c"
timer = timer_path.read_text()
timer = replace_once(timer, "static int __init a6_timer_init(struct device_node *node)",
                     "static int __init a6_cpu1_timer_init(struct device_node *node);\n\n"
                     "static int __init a6_timer_init(struct device_node *node)")
timer = replace_once(timer, '\tpr_info("A6 timer: counter %u Hz, IRQ %d\\n", a6_counter_rate, irq);\n\treturn 0;',
                     '\tpr_info("A6 timer: counter %u Hz, IRQ %d\\n", a6_counter_rate, irq);\n'
                     '\treturn a6_cpu1_timer_init(node);')
timer += "\n" + (repo / "kernel/platform/a6-timer-smp.inc").read_text()
if os.environ.get("A6_SMP_SCHEDULING") == "1":
    timer = timer.replace("checkpoint=explicit_before_rcu", "checkpoint=normal_starting")

# Validate all textual anchors before modifying any staged file.
for path, text in ((head_path, head), (smp_path, smp), (cpuhp_path, cpuhp),
                   (aic_path, aic), (timer_path, timer)):
    path.write_text(text)
irq_root = linux / "drivers/irqchip"
for name in ("a6-smp.c", "a6-smp-layout.h", "a6-smp-shootdown.inc"):
    (irq_root / name).write_bytes((repo / "kernel/platform" / name).read_bytes())
(irq_root / "a6-smp-bridge-blob.h").write_bytes((output / "a6-smp-bridge-blob.h").read_bytes())
with (irq_root / "Makefile").open("a") as stream:
    profile = "SCHEDULING" if os.environ.get("A6_SMP_SCHEDULING") == "1" else "QUARANTINE"
    stream.write(f"\nobj-y += a6-smp.o\nCFLAGS_a6-smp.o += -DA6_SMP_{profile}=1\n")
    if os.environ.get("A6_SMP_TIMER_LINE_PROBE") == "1":
        stream.write("CFLAGS_a6-smp.o += -DA6_SMP_TIMER_LINE_PROBE=1\n")
print("A6 SMP bridge installed: immutable handoff, CPU1 timer, pre-online quarantine")

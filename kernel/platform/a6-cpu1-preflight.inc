// SPDX-License-Identifier: GPL-2.0-only
/* Read-only N42 CPU1 preflight. No PMGR writes or secondary release. */
#include <linux/io.h>
#include <linux/kobject.h>
#include <linux/sysfs.h>
#include <asm/memory.h>

#define A6_CPU1_PMGR_BASE 0x3f101000
static void __iomem *a6_cpu1_pmgr;
static unsigned int a6_cpu1_release_writes;

static ssize_t a6_cpu1_preflight_show(struct kobject *kobj,
                                     struct kobj_attribute *attr, char *buf)
{
    u32 mmfr1, mmfr3, sctlr, pwr, enable, trigger;

    if (!a6_cpu1_pmgr)
        return -ENODEV;
    asm volatile("mrc p15, 0, %0, c0, c1, 5" : "=r"(mmfr1));
    asm volatile("mrc p15, 0, %0, c0, c1, 7" : "=r"(mmfr3));
    asm volatile("mrc p15, 0, %0, c1, c0, 0" : "=r"(sctlr));
    pwr = readl_relaxed(a6_cpu1_pmgr + 0x210);
    enable = readl_relaxed(a6_cpu1_pmgr + 0x214);
    trigger = readl_relaxed(a6_cpu1_pmgr + 0x220);
    return sysfs_emit(buf,
        "A6_CPU1_PREFLIGHT_V2 mmfr3=%08x sctlr=%08x pmgr_1210=%08x pmgr_1214=%08x pmgr_1220=%08x release_writes=%u mmfr1=%08x\n",
        mmfr3, sctlr, pwr, enable, trigger, a6_cpu1_release_writes, mmfr1);
}

#ifndef A6_CPU1_ALIAS_PREFLIGHT
/* Read only the known System RAM base, never the unproved physical-zero
 * alias. These bytes need not still hold Apple's reset dispatcher. Do not
 * interpret this observation as proof of the CPU1 fetch address.
 */
static ssize_t a6_cpu1_ram_base_show(struct kobject *kobj,
                                    struct kobj_attribute *attr, char *buf)
{
    unsigned int offset;
    ssize_t used = 0;
    const u32 *base = phys_to_virt(0x80000000);

    for (offset = 0; offset < 0x280; offset += 16) {
        if (offset >= 0x40 && offset < 0x200)
            continue;
        used += sysfs_emit_at(buf, used, "%08x: %08x %08x %08x %08x\n",
            0x80000000 + offset,
            READ_ONCE(base[offset / 4]), READ_ONCE(base[offset / 4 + 1]),
            READ_ONCE(base[offset / 4 + 2]), READ_ONCE(base[offset / 4 + 3]));
    }
    return used;
}

#endif

static struct kobj_attribute a6_cpu1_preflight_attr =
    __ATTR(status, 0444, a6_cpu1_preflight_show, NULL);

#ifndef A6_CPU1_ALIAS_PREFLIGHT
static struct kobj_attribute a6_cpu1_ram_base_attr =
    __ATTR(ram_base_snapshot, 0400, a6_cpu1_ram_base_show, NULL);
#endif
static struct attribute *a6_cpu1_preflight_attrs[] = {
    &a6_cpu1_preflight_attr.attr,
#ifndef A6_CPU1_ALIAS_PREFLIGHT
    &a6_cpu1_ram_base_attr.attr,
#endif
    NULL
};
static const struct attribute_group a6_cpu1_preflight_group = {
    .name = "a6_cpu1_preflight", .attrs = a6_cpu1_preflight_attrs
};

static int __init a6_cpu1_preflight_init(void)
{
    int ret;

    if (!of_machine_is_compatible("apple,n42ap"))
        return 0;
    a6_cpu1_pmgr = ioremap(A6_CPU1_PMGR_BASE, 0x1000);
    if (!a6_cpu1_pmgr)
        return -ENOMEM;
    ret = sysfs_create_group(firmware_kobj, &a6_cpu1_preflight_group);
    if (ret) {
        iounmap(a6_cpu1_pmgr);
        a6_cpu1_pmgr = NULL;
    }
    return ret;
}
late_initcall(a6_cpu1_preflight_init);

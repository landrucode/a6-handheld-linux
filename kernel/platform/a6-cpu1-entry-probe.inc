// SPDX-License-Identifier: GPL-2.0-only
/* Opt-in first contact; IPI profile owns fixed low vectors on CPU1. */
#include <linux/delay.h>
#include <linux/jiffies.h>
#include <asm/cp15.h>
#include "a6-cpu1-entry-blob.inc"
#if A6_ENTRY_TLBI_PROBE
#if A6_ENTRY_CACHE_PROBE
#include "a6-cpu1-cache-layout.inc"
#include "a6-cpu1-cache-map.inc"
#else
#include "a6-cpu1-tlbi-layout.inc"
#endif
#endif

static bool a6_entry_attempted, a6_entry_vector_installed;
static int a6_entry_result;
static u32 a6_entry_original[16], a6_entry_marker[7];
static u32 a6_entry_before[3], a6_entry_after[3], a6_entry_cpu0_sctlr, a6_entry_cpu0_actlr, a6_entry_cpu1_mmu_sctlr, a6_entry_cpu1_actlr;
#ifdef A6_CPU1_CACHE_TRE_PROBE
static u32 a6_entry_cpu1_prrr, a6_entry_cpu1_nmrr;
#endif

static void a6_entry_probe_run(void)
{
    void __iomem *ram = NULL, *zero = NULL, *mailbox = NULL;
    unsigned long deadline;
    unsigned int i;
    u32 observed;
    int result = 0;

    a6_entry_attempted = true;
    a6_entry_cpu0_sctlr = get_cr();
#if A6_ENTRY_TLBI_PROBE
    asm volatile("mrc p15, 0, %0, c1, c0, 1" : "=r" (a6_entry_cpu0_actlr));
#endif
    if (A6_ENTRY_FIXED_VECTORS && !(a6_entry_cpu0_sctlr & CR_V)) {
        result = -EPERM;
        goto done;
    }
    if (!a6_alias_write_attempted || a6_alias_write_result || !a6_cpu1_pmgr ||
        !READ_ONCE(a6_auto_enabled) || !READ_ONCE(a6_auto_attached) || READ_ONCE(a6_auto_fault) ||
        !READ_ONCE(a6_low_enabled) || READ_ONCE(a6_low_triggered)) {
        result = -EPERM;
        goto done;
    }
    ram = ioremap(0x80000000, 4096);
    zero = ioremap(0, 4096);
    mailbox = ioremap(0x83ffe000, 4096);
    if (!ram || !zero || !mailbox) {
        result = -ENOMEM;
        goto done;
    }
    /* Check originals before installing any code or vector. */
    for (i = 0; i < (A6_ENTRY_FIXED_VECTORS ? 16 : 2); i++) {
        result = a6_alias_read_word(ram + i * 4, &a6_entry_original[i]);
        if (!result)
            result = a6_alias_read_word(zero + i * 4, &observed);
        if (result)
            goto done;
        if (observed != a6_entry_original[i] || observed != a6_cpu1_alias_data[0][i]) {
            result = -ESTALE;
            goto done;
        }
    }
#if A6_ENTRY_TLBI_PROBE
    result = a6_tlbi_install();
    if (result)
        goto done;
#if A6_ENTRY_CACHE_PROBE
    result = a6_cache_cpu0_map();
    if (result)
        goto done;
#endif
#endif
    for (i = 0; i < 24; i++)
        writel(0, mailbox + 0x200 + i * 4);
    for (i = 0; i < ARRAY_SIZE(a6_entry_blob); i++)
        writel(a6_entry_blob[i], mailbox + i * 4);
    if (A6_ENTRY_IRQ_PA && !A6_ENTRY_FIXED_VECTORS) {
        for (i = 0; i < 8; i++) {
            writel(0xe59ff018, mailbox + 0x400 + i * 4);
            writel(i == 6 ? A6_ENTRY_IRQ_PA : A6_ENTRY_PARK_PA,
                   mailbox + 0x420 + i * 4);
        }
        dsb(sy);
        for (i = 0; i < 8; i++) {
            if (readl(mailbox + 0x400 + i * 4) != 0xe59ff018 ||
                readl(mailbox + 0x420 + i * 4) !=
                    (i == 6 ? A6_ENTRY_IRQ_PA : A6_ENTRY_PARK_PA)) {
                result = -EIO;
                goto done;
            }
        }
    }
    dsb(sy);
    for (i = 0; i < ARRAY_SIZE(a6_entry_blob); i++) {
        if (readl(mailbox + i * 4) != a6_entry_blob[i]) {
            result = -EIO;
            goto done;
        }
    }
    if (A6_ENTRY_FIXED_VECTORS) {
        /* No Security Extensions: VBAR is unavailable. CPU1 uses fixed
         * low vectors with MMU off. CPU0 retains its Linux virtual vectors.
         * Install literals before all eight vector instructions. */
        for (i = 0; i < 8; i++)
            writel(i == 0 ? 0x83ffe000 :
                   (i == 3 || i == 4) && (A6_ENTRY_ABORT_PA != 0) ? A6_ENTRY_ABORT_PA :
                   i == 6 ? A6_ENTRY_IRQ_PA : A6_ENTRY_PARK_PA,
                   ram + 0x20 + i * 4);
        for (i = 0; i < 8; i++)
            writel(0xe59ff018, ram + i * 4);
    } else {
        /* Original first-contact reset trampoline. */
        writel(0x83ffe000, ram + 4);
        writel(0xe51ff004, ram);
    }
    dsb(sy);
    a6_entry_vector_installed = true;
    for (i = 0; i < (A6_ENTRY_FIXED_VECTORS ? 16 : 2); i++) {
        u32 expected;
        if (A6_ENTRY_FIXED_VECTORS)
            expected = i < 8 ? 0xe59ff018 : i == 8 ? 0x83ffe000 :
                       (i == 11 || i == 12) && (A6_ENTRY_ABORT_PA != 0) ? A6_ENTRY_ABORT_PA :
                       i == 14 ? A6_ENTRY_IRQ_PA : A6_ENTRY_PARK_PA;
        else
            expected = i ? 0x83ffe000 : 0xe51ff004;
        result = a6_alias_read_word(zero + i * 4, &observed);
        if (!result && observed != expected)
            result = -EIO;
        if (result) {
            /* No release yet: restore every modified word on failure. */
            for (i = A6_ENTRY_FIXED_VECTORS ? 16 : 2; i > 0; i--)
                writel(a6_entry_original[i - 1], ram + (i - 1) * 4);
            dsb(sy);
            a6_entry_vector_installed = false;
            goto done;
        }
    }
    a6_entry_before[0] = readl(a6_cpu1_pmgr + 0x210);
    a6_entry_before[1] = readl(a6_cpu1_pmgr + 0x214);
    a6_entry_before[2] = readl(a6_cpu1_pmgr + 0x220);
    /* Exact stock N42 enable ordering, CPU1 mask only. */
    writel(2, a6_cpu1_pmgr + 0x214);
    a6_cpu1_release_writes++;
    dsb(sy);
    writel(2, a6_cpu1_pmgr + 0x220);
    a6_cpu1_release_writes++;
    dsb(sy);
    deadline = jiffies + msecs_to_jiffies(5000);
    do {
        if (readl(mailbox + 0x200) == A6_ENTRY_EXPECTED_STAGE)
            break;
        msleep(10);
    } while (time_before(jiffies, deadline));
    for (i = 0; i < 7; i++)
        a6_entry_marker[i] = readl(mailbox + 0x200 + i * 4);
#if A6_ENTRY_TLBI_PROBE
    a6_entry_cpu1_mmu_sctlr = readl(mailbox + 0x244);
    a6_entry_cpu1_actlr = readl(mailbox + 0x25c);
#ifdef A6_CPU1_CACHE_TRE_PROBE
    a6_entry_cpu1_prrr = readl(mailbox + 0x260);
    a6_entry_cpu1_nmrr = readl(mailbox + 0x264);
    if ((a6_entry_cpu1_mmu_sctlr & 0x10001005) != 0x10000005 ||
        a6_entry_cpu1_prrr != a6_cache_cpu0_prrr ||
        a6_entry_cpu1_nmrr != a6_cache_cpu0_nmrr)
        result = -EPROTO;
#else
    if ((a6_entry_cpu1_mmu_sctlr & 0x1005) !=
        (A6_ENTRY_CACHE_PROBE ? 5 : 1))
        result = -EPROTO;
#endif
#endif
    if (a6_entry_marker[0] != A6_ENTRY_EXPECTED_STAGE || a6_entry_marker[1] != 0xa6c10001 ||
        (a6_entry_marker[2] & 0x1005) || (a6_entry_marker[3] & 0xff) != 1 ||
        ((a6_entry_marker[6] >> 12) & 0xf))
        result = -ETIMEDOUT;
    a6_entry_after[0] = readl(a6_cpu1_pmgr + 0x210);
    a6_entry_after[1] = readl(a6_cpu1_pmgr + 0x214);
    a6_entry_after[2] = readl(a6_cpu1_pmgr + 0x220);
    /* Keep the vector/private code after release, including on timeout.
     * A late entry must not fetch restored image data. Next DFU resets it.
     */
done:
    if (mailbox)
        iounmap(mailbox);
    if (zero)
        iounmap(zero);
    if (ram)
        iounmap(ram);
    a6_entry_result = result;
    pr_info("A6_CPU1_ENTRY_V1 result=%d stage=%u sctlr=%08x mpidr=%08x cpsr=%08x midr=%08x pfr1=%08x release_writes=%u vector_installed=%u\n",
            result, a6_entry_marker[0], a6_entry_marker[2], a6_entry_marker[3],
            a6_entry_marker[4], a6_entry_marker[5], a6_entry_marker[6],
            a6_cpu1_release_writes, a6_entry_vector_installed);
}

static ssize_t a6_entry_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
    ssize_t result;

    mutex_lock(&a6_cpu1_alias_lock);
    result = sysfs_emit(buf,
        "A6_CPU1_ENTRY_V1 attempted=%u result=%d stage=%u magic=%08x sctlr=%08x mpidr=%08x cpsr=%08x midr=%08x pfr1=%08x release_writes=%u vector_installed=%u\n"
        "cpu0_sctlr=%08x cpu0_actlr=%08x fixed_vectors=%u cpu1_mmu_sctlr=%08x cpu1_actlr=%08x original0=%08x original4=%08x before_1210_1214_1220=%08x/%08x/%08x after=%08x/%08x/%08x\n"
#ifdef A6_CPU1_CACHE_TRE_PROBE
        "cpu1_prrr=%08x cpu1_nmrr=%08x\n"
#endif
        ,
        a6_entry_attempted, a6_entry_result, a6_entry_marker[0], a6_entry_marker[1],
        a6_entry_marker[2], a6_entry_marker[3], a6_entry_marker[4], a6_entry_marker[5],
        a6_entry_marker[6], a6_cpu1_release_writes, a6_entry_vector_installed,
        a6_entry_cpu0_sctlr, a6_entry_cpu0_actlr, A6_ENTRY_FIXED_VECTORS, a6_entry_cpu1_mmu_sctlr, a6_entry_cpu1_actlr, a6_entry_original[0], a6_entry_original[1], a6_entry_before[0], a6_entry_before[1],
        a6_entry_before[2], a6_entry_after[0], a6_entry_after[1], a6_entry_after[2]
#ifdef A6_CPU1_CACHE_TRE_PROBE
        , a6_entry_cpu1_prrr, a6_entry_cpu1_nmrr
#endif
        );
    mutex_unlock(&a6_cpu1_alias_lock);
    return result;
}

static ssize_t a6_entry_store(struct kobject *kobj, struct kobj_attribute *attr,
                              const char *buf, size_t count)
{
    int result;

    if (!sysfs_streq(buf, "start"))
        return -EINVAL;
    mutex_lock(&a6_cpu1_alias_lock);
    if (a6_entry_attempted) {
        mutex_unlock(&a6_cpu1_alias_lock);
        return -EALREADY;
    }
    a6_entry_probe_run();
    result = a6_entry_result;
    mutex_unlock(&a6_cpu1_alias_lock);
    return result ? result : count;
}

static struct kobj_attribute a6_entry_attr =
    __ATTR(entry_probe, 0600, a6_entry_show, a6_entry_store);

#if A6_ENTRY_IRQ_PA
#include "a6-cpu1-ipi-probe.inc"
#if A6_ENTRY_TLBI_PROBE
#if A6_ENTRY_CACHE_PROBE
#include "a6-cpu1-cache-test.inc"
#else
#include "a6-cpu1-tlbi-test.inc"
#endif
#endif
#endif

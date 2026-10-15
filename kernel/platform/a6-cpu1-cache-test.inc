// SPDX-License-Identifier: GPL-2.0-only
/* One bounded, CPU1-private read-visibility experiment. No scheduler entry. */
#include <asm/cacheflush.h>

static bool a6_cache_attempted;
static int a6_cache_result;
static u32 a6_cache_sent, a6_cache_seen[3][5];
#ifdef A6_CPU1_CACHE_REPEAT_PROBE
static u32 a6_cache_repeat_hits, a6_cache_repeat_stale;
static u32 a6_cache_repeat_new_mask, a6_cache_repeat_stale_mask;
static u32 a6_cache_repeat_last_tag, a6_cache_repeat_last_value;
#endif
static const u32 a6_cache_tags[3] = {
    0xa6c50001, 0xa6c50002, 0xa6c50003
};
static const u32 a6_cache_commands[3] = { 6, 5, 6 };
static const u32 a6_cache_values[3] = {
    A6_TLBI_A_VALUE, A6_TLBI_B_VALUE, A6_TLBI_B_VALUE
};

static void a6_cache_prove(void)
{
    void __iomem *aic = NULL, *mailbox = NULL;
    volatile u32 *word = a6_cache_cpu0_view;
    unsigned long deadline;
    unsigned int phase;
    int result = 0;

    a6_cache_attempted = true;
    if (!a6_entry_attempted || a6_entry_result || !a6_ipi_attempted ||
        a6_ipi_result || a6_ipi_send_writes != 2 || !word ||
#ifdef A6_CPU1_CACHE_SHAREABLE_PROBE
        a6_cache_cpu0_hw_pte != 0x83ff641f ||
        a6_cache_cpu1_pte != 0x83ff6c3e ||
#endif
        (a6_entry_cpu1_mmu_sctlr & 0x10001005) !=
#ifdef A6_CPU1_CACHE_TRE_PROBE
            0x10000005 ||
#else
            5 ||
#endif
        !READ_ONCE(a6_auto_attached) || READ_ONCE(a6_auto_fault) ||
        !READ_ONCE(a6_low_enabled) || READ_ONCE(a6_low_triggered)) {
        result = -EPERM;
        goto done;
    }
    aic = ioremap(0x3f200000, 0x10000);
    mailbox = ioremap(0x83ffe000, 0x1000);
    if (!aic || !mailbox) {
        result = -ENOMEM;
        goto done;
    }
    if (readl(mailbox + 0x21c) != 2 || readl(mailbox + 0x22c) ||
        readl(mailbox + 0x200) != 4) {
        result = -ESTALE;
        goto done;
    }
    for (phase = 0; phase < 3; phase++) {
        u32 tag = a6_cache_tags[phase];

        WRITE_ONCE(*word, a6_cache_values[phase]);
        if (phase != 1)
            __cpuc_flush_dcache_area((void *)word, sizeof(*word));
        dsb(sy);
        writel(a6_cache_commands[phase], mailbox + 0x23c);
        writel(tag, mailbox + 0x234);
        dsb(sy);
        writel(2, aic + 0x2008);
        a6_cache_sent++;
        dsb(sy);
        deadline = jiffies + msecs_to_jiffies(5000);
        do {
            if (readl(mailbox + 0x230) == tag ||
                readl(mailbox + 0x22c) || readl(mailbox + 0x200) == 254)
                break;
            msleep(10);
        } while (time_before(jiffies, deadline));
        a6_cache_seen[phase][0] = readl(mailbox + 0x21c);
        a6_cache_seen[phase][1] = readl(mailbox + 0x220);
        a6_cache_seen[phase][2] = readl(mailbox + 0x230);
        a6_cache_seen[phase][3] = readl(mailbox + 0x238);
        a6_cache_seen[phase][4] = readl(mailbox + 0x22c);
        if (a6_cache_seen[phase][0] != phase + 3 ||
            a6_cache_seen[phase][1] != 0x00040001 ||
            a6_cache_seen[phase][2] != tag ||
            a6_cache_seen[phase][4]) {
            result = -ETIMEDOUT;
            break;
        }
        /* Phase 1 is deliberately observational: B might be visible
         * through coherence or because CPU1 evicted its cached A line.
         */
        if (phase != 1 && a6_cache_seen[phase][3] != a6_cache_values[phase]) {
            result = -EPROTO;
            break;
        }
        if (phase == 1 && a6_cache_seen[phase][3] != A6_TLBI_A_VALUE &&
            a6_cache_seen[phase][3] != A6_TLBI_B_VALUE) {
            result = -EPROTO;
            break;
        }
    }
#ifdef A6_CPU1_CACHE_REPEAT_PROBE
    /* Phase 2 left B in CPU1's cache. Alternate CPU0's dirty WB word
     * without maintenance; CPU1 only reads. Its private code, stack and
     * marker are NC, so this maximises line retention without claiming
     * that a cache hit is architecturally guaranteed on every IRQ.
     */
    for (phase = 0; !result && phase < 32; phase++) {
        u32 expected = (phase & 1) ? A6_TLBI_B_VALUE : A6_TLBI_A_VALUE;
        u32 previous = (phase & 1) ? A6_TLBI_A_VALUE : A6_TLBI_B_VALUE;
        u32 tag = 0xa6c60001 + phase;
        u32 count, event, ack, value, fatal;

        WRITE_ONCE(*word, expected);
        dsb(sy);
        writel(5, mailbox + 0x23c); /* read without invalidate */
        writel(tag, mailbox + 0x234);
        dsb(sy);
        writel(2, aic + 0x2008);
        a6_cache_sent++;
        dsb(sy);
        deadline = jiffies + msecs_to_jiffies(5000);
        do {
            if (readl(mailbox + 0x230) == tag ||
                readl(mailbox + 0x22c) || readl(mailbox + 0x200) == 254)
                break;
            msleep(10);
        } while (time_before(jiffies, deadline));
        count = readl(mailbox + 0x21c);
        event = readl(mailbox + 0x220);
        ack = readl(mailbox + 0x230);
        value = readl(mailbox + 0x238);
        fatal = readl(mailbox + 0x22c);
        a6_cache_repeat_last_tag = tag;
        a6_cache_repeat_last_value = value;
        if (count != phase + 6 || event != 0x00040001 ||
            ack != tag || fatal) {
            result = -ETIMEDOUT;
            break;
        }
        if (value == expected) {
            a6_cache_repeat_hits++;
            a6_cache_repeat_new_mask |= BIT(phase);
        } else if (value == previous) {
            a6_cache_repeat_stale++;
            a6_cache_repeat_stale_mask |= BIT(phase);
        } else {
            result = -EPROTO;
            break;
        }
    }
    /* Final explicit maintenance restores a known state even if every
     * unmaintained read was stale. CPU0's last written value is B.
     */
    if (!result) {
        u32 tag = 0xa6c60021;

        __cpuc_flush_dcache_area((void *)word, sizeof(*word));
        dsb(sy);
        writel(6, mailbox + 0x23c);
        writel(tag, mailbox + 0x234);
        dsb(sy);
        writel(2, aic + 0x2008);
        a6_cache_sent++;
        dsb(sy);
        deadline = jiffies + msecs_to_jiffies(5000);
        do {
            if (readl(mailbox + 0x230) == tag ||
                readl(mailbox + 0x22c) || readl(mailbox + 0x200) == 254)
                break;
            msleep(10);
        } while (time_before(jiffies, deadline));
        a6_cache_repeat_last_tag = tag;
        a6_cache_repeat_last_value = readl(mailbox + 0x238);
        if (readl(mailbox + 0x21c) != 38 ||
            readl(mailbox + 0x220) != 0x00040001 ||
            readl(mailbox + 0x230) != tag || readl(mailbox + 0x22c) ||
            a6_cache_repeat_last_value != A6_TLBI_B_VALUE)
            result = -EPROTO;
    }
#endif
done:
    /* The CPU0 mapping is retained after a failed run so no subsequent
     * device alias is created while CPU1 might hold the cached line.
     */
    if (mailbox)
        iounmap(mailbox);
    if (aic)
        iounmap(aic);
    a6_cache_result = result;
    pr_info("A6_CPU1_CACHE_V1 result=%d sent=%u cpu0_pte=%08x cpu1_pte=%08x warm=%08x no_maint=%08x maintained=%08x\n",
            result, a6_cache_sent, a6_cache_cpu0_hw_pte, a6_cache_cpu1_pte,
            a6_cache_seen[0][3], a6_cache_seen[1][3], a6_cache_seen[2][3]);
}

static ssize_t a6_cache_show(struct kobject *kobj,
                             struct kobj_attribute *attr, char *buf)
{
    ssize_t used;
    unsigned int phase;

    mutex_lock(&a6_cpu1_alias_lock);
    used = sysfs_emit(buf,
        "A6_CPU1_CACHE_V1 attempted=%u result=%d sent=%u cpu0_hw_pte=%08x cpu1_pte=%08x cpu0_sctlr=%08x cpu1_sctlr=%08x cpu0_prrr=%08x cpu0_nmrr=%08x\n",
        a6_cache_attempted, a6_cache_result, a6_cache_sent,
        a6_cache_cpu0_hw_pte, a6_cache_cpu1_pte, a6_cache_cpu0_sctlr,
        a6_entry_cpu1_mmu_sctlr, a6_cache_cpu0_prrr, a6_cache_cpu0_nmrr);
#ifdef A6_CPU1_CACHE_TRE_PROBE
    used += sysfs_emit_at(buf, used, "cpu1_prrr=%08x cpu1_nmrr=%08x\n",
                          a6_entry_cpu1_prrr, a6_entry_cpu1_nmrr);
#endif
    for (phase = 0; phase < 3; phase++)
        used += sysfs_emit_at(buf, used,
            "phase=%u tag=%08x cmd=%u count=%u event=%08x ack=%08x value=%08x fatal=%u\n",
            phase, a6_cache_tags[phase], a6_cache_commands[phase],
            a6_cache_seen[phase][0], a6_cache_seen[phase][1],
            a6_cache_seen[phase][2], a6_cache_seen[phase][3],
            a6_cache_seen[phase][4]);
#ifdef A6_CPU1_CACHE_REPEAT_PROBE
    used += sysfs_emit_at(buf, used,
        "repeat=32 new=%u stale=%u new_mask=%08x stale_mask=%08x last_tag=%08x last_value=%08x\n",
        a6_cache_repeat_hits, a6_cache_repeat_stale,
        a6_cache_repeat_new_mask, a6_cache_repeat_stale_mask,
        a6_cache_repeat_last_tag, a6_cache_repeat_last_value);
#endif
    mutex_unlock(&a6_cpu1_alias_lock);
    return used;
}

static ssize_t a6_cache_store(struct kobject *kobj, struct kobj_attribute *attr,
                              const char *buf, size_t count)
{
    int result;

    if (!sysfs_streq(buf, "prove"))
        return -EINVAL;
    mutex_lock(&a6_cpu1_alias_lock);
    if (a6_cache_attempted) {
        mutex_unlock(&a6_cpu1_alias_lock);
        return -EALREADY;
    }
    a6_cache_prove();
    result = a6_cache_result;
    mutex_unlock(&a6_cpu1_alias_lock);
    return result ? result : count;
}

static struct kobj_attribute a6_cache_attr =
    __ATTR(cache_proof, 0600, a6_cache_show, a6_cache_store);

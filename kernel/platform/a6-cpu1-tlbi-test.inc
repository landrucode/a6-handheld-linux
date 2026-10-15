// SPDX-License-Identifier: GPL-2.0-only
/* One bounded CPU0 page-table-change -> CPU1 local-TLBI diagnostic. */
static bool a6_tlbi_attempted;
static int a6_tlbi_result;
static u32 a6_tlbi_sent;
static u32 a6_tlbi_seen[5][7];
static const u32 a6_tlbi_tags[5] = {
    0xa6d10001, 0xa6d10002, 0xa6d10003, 0xa6d10004, 0xa6d10005
};
static const u32 a6_tlbi_commands[5] = { 1, 1, 2, 3, 4 };
static const u32 a6_tlbi_values[5] = {
    A6_TLBI_A_VALUE, A6_TLBI_A_VALUE, A6_TLBI_B_VALUE,
    A6_TLBI_A_VALUE, A6_TLBI_B_VALUE
};

static void a6_tlbi_prove(void)
{
    void __iomem *aic = NULL, *mailbox = NULL, *l2 = NULL;
    unsigned long deadline;
    unsigned int phase;
    int result = 0;

    a6_tlbi_attempted = true;
    if (!a6_entry_attempted || a6_entry_result || !a6_ipi_attempted ||
        a6_ipi_result || a6_ipi_send_writes != 2 ||
        (a6_entry_cpu1_mmu_sctlr & 0x1005) != 1 ||
        !READ_ONCE(a6_auto_attached) || READ_ONCE(a6_auto_fault) ||
        !READ_ONCE(a6_low_enabled) || READ_ONCE(a6_low_triggered)) {
        result = -EPERM;
        goto done;
    }
    aic = ioremap(0x3f200000, 0x10000);
    mailbox = ioremap(0x83ffe000, 0x1000);
    l2 = ioremap(A6_TLBI_L2_PA, 0x1000);
    if (!aic || !mailbox || !l2) {
        result = -ENOMEM;
        goto done;
    }
    if (readl(l2) != A6_TLBI_PTE_A || readl(mailbox + 0x22c) ||
        readl(mailbox + 0x21c) != 2) {
        result = -ESTALE;
        goto done;
    }
    for (phase = 0; phase < 5; phase++) {
        u32 tag = a6_tlbi_tags[phase];

        if (phase == 1 || phase == 4)
            writel(A6_TLBI_PTE_B, l2);
        else if (phase == 3)
            writel(A6_TLBI_PTE_A, l2);
        dsb(sy);
        if (readl(l2) != ((phase == 0 || phase == 3) ?
                           A6_TLBI_PTE_A : A6_TLBI_PTE_B)) {
            result = -EIO;
            break;
        }
        writel(a6_tlbi_commands[phase], mailbox + 0x23c);
        writel(tag, mailbox + 0x234);
        dsb(sy);
        writel(2, aic + 0x2008);
        a6_tlbi_sent++;
        dsb(sy);
        deadline = jiffies + msecs_to_jiffies(5000);
        do {
            if (readl(mailbox + 0x230) == tag ||
                readl(mailbox + 0x22c) || readl(mailbox + 0x200) == 254)
                break;
            msleep(10);
        } while (time_before(jiffies, deadline));
        a6_tlbi_seen[phase][0] = readl(mailbox + 0x21c); /* count */
        a6_tlbi_seen[phase][1] = readl(mailbox + 0x220); /* event */
        a6_tlbi_seen[phase][2] = readl(mailbox + 0x224); /* SPSR */
        a6_tlbi_seen[phase][3] = readl(mailbox + 0x240); /* IRQ CPSR */
        a6_tlbi_seen[phase][4] = readl(mailbox + 0x230); /* ACK tag */
        a6_tlbi_seen[phase][5] = readl(mailbox + 0x238); /* CPU1 value */
        a6_tlbi_seen[phase][6] = readl(mailbox + 0x22c); /* fatal */
        if (a6_tlbi_seen[phase][0] != phase + 3 ||
            a6_tlbi_seen[phase][1] != 0x00040001 ||
            (a6_tlbi_seen[phase][2] & 0x9f) != 0x13 ||
            (a6_tlbi_seen[phase][3] & 0x9f) != 0x92 ||
            a6_tlbi_seen[phase][4] != tag || a6_tlbi_seen[phase][6]) {
            result = -ETIMEDOUT;
            break;
        }
        if (a6_tlbi_seen[phase][5] != a6_tlbi_values[phase]) {
            /* No stale translation in the no-flush control = inconclusive. */
            result = phase == 1 ? -ENODATA : -EPROTO;
            break;
        }
    }
done:
    if (l2)
        iounmap(l2);
    if (mailbox)
        iounmap(mailbox);
    if (aic)
        iounmap(aic);
    a6_tlbi_result = result;
    pr_info("A6_CPU1_TLBI_V1 result=%d sent=%u stale=%08x page=%08x asid=%08x full=%08x\n",
            result, a6_tlbi_sent, a6_tlbi_seen[1][5], a6_tlbi_seen[2][5],
            a6_tlbi_seen[3][5], a6_tlbi_seen[4][5]);
}

static ssize_t a6_tlbi_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
    ssize_t used;
    unsigned int phase;
    void __iomem *mailbox;
    u32 stage = 0, dfsr = 0, dfar = 0, fault_spsr = 0, fault_lr = 0;

    mutex_lock(&a6_cpu1_alias_lock);
    mailbox = ioremap(0x83ffe000, 0x1000);
    if (mailbox) {
        stage = readl(mailbox + 0x200);
        dfsr = readl(mailbox + 0x24c);
        dfar = readl(mailbox + 0x250);
        fault_spsr = readl(mailbox + 0x254);
        fault_lr = readl(mailbox + 0x258);
        iounmap(mailbox);
    }
    used = sysfs_emit(buf,
        "A6_CPU1_TLBI_V1 attempted=%u result=%d sent=%u stage=%u mmu_sctlr=%08x cpu0_actlr=%08x cpu1_actlr=%08x dfsr=%08x dfar=%08x fault_spsr=%08x fault_lr=%08x\n",
        a6_tlbi_attempted, a6_tlbi_result, a6_tlbi_sent, stage,
        a6_entry_cpu1_mmu_sctlr, a6_entry_cpu0_actlr, a6_entry_cpu1_actlr,
        dfsr, dfar, fault_spsr, fault_lr);
    for (phase = 0; phase < 5; phase++)
        used += sysfs_emit_at(buf, used,
            "phase=%u tag=%08x cmd=%u count=%u event=%08x spsr=%08x irq_cpsr=%08x ack=%08x value=%08x fatal=%u\n",
            phase, a6_tlbi_tags[phase], a6_tlbi_commands[phase],
            a6_tlbi_seen[phase][0], a6_tlbi_seen[phase][1],
            a6_tlbi_seen[phase][2], a6_tlbi_seen[phase][3],
            a6_tlbi_seen[phase][4], a6_tlbi_seen[phase][5],
            a6_tlbi_seen[phase][6]);
    mutex_unlock(&a6_cpu1_alias_lock);
    return used;
}

static ssize_t a6_tlbi_store(struct kobject *kobj, struct kobj_attribute *attr,
                             const char *buf, size_t count)
{
    int result;

    if (!sysfs_streq(buf, "prove"))
        return -EINVAL;
    mutex_lock(&a6_cpu1_alias_lock);
    if (a6_tlbi_attempted) {
        mutex_unlock(&a6_cpu1_alias_lock);
        return -EALREADY;
    }
    a6_tlbi_prove();
    result = a6_tlbi_result;
    mutex_unlock(&a6_cpu1_alias_lock);
    return result ? result : count;
}

static struct kobj_attribute a6_tlbi_attr =
    __ATTR(tlbi_proof, 0600, a6_tlbi_show, a6_tlbi_store);

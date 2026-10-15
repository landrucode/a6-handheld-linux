// SPDX-License-Identifier: GPL-2.0-only
/* CPU0 sends twice; only CPU1's IRQ handler reads its local AIC EVENT. */
static bool a6_ipi_attempted;
static int a6_ipi_result;
static u32 a6_ipi_observed[2][6];
static const u32 a6_ipi_tags[2] = { 0xa6c10101, 0xa6c10202 };
static unsigned int a6_ipi_send_writes;

static void a6_ipi_prove(void)
{
    void __iomem *aic = NULL, *mailbox = NULL;
    unsigned int phase;
    unsigned long deadline;
    int result = 0;

    a6_ipi_attempted = true;
    if (!a6_entry_attempted || a6_entry_result || a6_entry_marker[0] != 3 ||
        a6_cpu1_release_writes != 2 || !READ_ONCE(a6_auto_attached) ||
        READ_ONCE(a6_auto_fault) || !READ_ONCE(a6_low_enabled) ||
        READ_ONCE(a6_low_triggered)) {
        result = -EPERM;
        goto done;
    }
    aic = ioremap(0x3f200000, 0x10000);
    mailbox = ioremap(0x83ffe000, 4096);
    if (!aic || !mailbox) {
        result = -ENOMEM;
        goto done;
    }
    if (readl(mailbox + 0x21c) || readl(mailbox + 0x22c)) {
        result = -ESTALE;
        goto done;
    }
    for (phase = 0; phase < 2; phase++) {
        writel(a6_ipi_tags[phase], mailbox + 0x234);
        dsb(sy);
        writel(2, aic + 0x2008); /* OTHER to CPU1, not CPU0 */
        a6_ipi_send_writes++;
        dsb(sy);
        deadline = jiffies + msecs_to_jiffies(5000);
        do {
            if (readl(mailbox + 0x230) == a6_ipi_tags[phase] ||
                readl(mailbox + 0x22c))
                break;
            msleep(10);
        } while (time_before(jiffies, deadline));
        a6_ipi_observed[phase][0] = readl(mailbox + 0x21c); /* count */
        a6_ipi_observed[phase][1] = readl(mailbox + 0x220); /* event */
        a6_ipi_observed[phase][2] = readl(mailbox + 0x224); /* SPSR */
        a6_ipi_observed[phase][3] = readl(mailbox + 0x240); /* IRQ CPSR */
        a6_ipi_observed[phase][4] = readl(mailbox + 0x230); /* ACK tag */
        a6_ipi_observed[phase][5] = readl(mailbox + 0x22c); /* fatal */
        if (a6_ipi_observed[phase][0] != phase + 1 ||
            a6_ipi_observed[phase][1] != 0x00040001 ||
            (a6_ipi_observed[phase][2] & 0x9f) != 0x13 ||
            (a6_ipi_observed[phase][3] & 0x9f) != 0x92 ||
            a6_ipi_observed[phase][4] != a6_ipi_tags[phase] ||
            a6_ipi_observed[phase][5]) {
            result = -ETIMEDOUT;
            break;
        }
    }
done:
    if (mailbox)
        iounmap(mailbox);
    if (aic)
        iounmap(aic);
    a6_ipi_result = result;
    pr_info("A6_CPU1_IPI_V1 result=%d send_writes=%u event0=%08x count0=%u event1=%08x count1=%u\n",
            result, a6_ipi_send_writes, a6_ipi_observed[0][1], a6_ipi_observed[0][0],
            a6_ipi_observed[1][1], a6_ipi_observed[1][0]);
}

static ssize_t a6_ipi_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
    ssize_t used;
    unsigned int phase;

    mutex_lock(&a6_cpu1_alias_lock);
    used = sysfs_emit(buf, "A6_CPU1_IPI_V1 attempted=%u result=%d send_writes=%u release_writes=%u\n",
                      a6_ipi_attempted, a6_ipi_result, a6_ipi_send_writes, a6_cpu1_release_writes);
    for (phase = 0; phase < 2; phase++)
        used += sysfs_emit_at(buf, used,
            "phase=%u tag=%08x count=%u event=%08x spsr=%08x irq_cpsr=%08x ack=%08x fatal=%u\n",
            phase, a6_ipi_tags[phase], a6_ipi_observed[phase][0], a6_ipi_observed[phase][1],
            a6_ipi_observed[phase][2], a6_ipi_observed[phase][3],
            a6_ipi_observed[phase][4], a6_ipi_observed[phase][5]);
    mutex_unlock(&a6_cpu1_alias_lock);
    return used;
}

static ssize_t a6_ipi_store(struct kobject *kobj, struct kobj_attribute *attr,
                            const char *buf, size_t count)
{
    int result;

    if (!sysfs_streq(buf, "prove"))
        return -EINVAL;
    mutex_lock(&a6_cpu1_alias_lock);
    if (a6_ipi_attempted) {
        mutex_unlock(&a6_cpu1_alias_lock);
        return -EALREADY;
    }
    a6_ipi_prove();
    result = a6_ipi_result;
    mutex_unlock(&a6_cpu1_alias_lock);
    return result ? result : count;
}

static struct kobj_attribute a6_ipi_attr =
    __ATTR(ipi_proof, 0600, a6_ipi_show, a6_ipi_store);

// SPDX-License-Identifier: GPL-2.0-only
/* Separate opt-in profile: reversible RAM-side alias proof, no trampoline. */
static bool a6_alias_write_attempted;
static int a6_alias_write_result;
static u32 a6_alias_original[2], a6_alias_restore_ram[2], a6_alias_restore_zero[2];
static u32 a6_alias_seen_ram[2][2], a6_alias_seen_zero[2][2];
static const u32 a6_alias_patterns[2][2] = {
    { 0xa6c15a3c, 0x59e2a5c3 }, { 0x3c5aa6c1, 0xc3a559e2 }
};

static int a6_alias_read_word(void __iomem *address, u32 *value)
{
    return copy_from_kernel_nofault(value, (const void __force *)address, sizeof(*value));
}

/* Process context under alias mutex. Device writes followed by DSB and
 * reads; every modified RAM word is restored before unmapping, even if
 * a pattern observation fails. Physical zero is never written directly.
 */
static void a6_alias_write_prove(void)
{
    void __iomem *ram = NULL, *zero = NULL;
    unsigned int page, phase;
    bool modified[2] = { false, false };
    int result = 0, error;

    a6_alias_write_attempted = true;
    a6_cpu1_alias_sample();
    if (a6_cpu1_alias_result || a6_cpu1_alias_words != 2048 ||
        a6_cpu1_alias_same[0] != 1024 || a6_cpu1_alias_same[1] != 1024 ||
        a6_cpu1_alias_nonzero_mask != 3) {
        result = -EPROTO;
        goto done;
    }
    ram = ioremap(0x80000000, 8192);
    zero = ioremap(0, 8192);
    if (!ram || !zero) {
        result = -ENOMEM;
        goto done;
    }
    /* Save and validate both words before the first write. */
    for (page = 0; page < 2; page++) {
        u32 observed;
        result = a6_alias_read_word(ram + page * PAGE_SIZE, &a6_alias_original[page]);
        if (result)
            goto done;
        result = a6_alias_read_word(zero + page * PAGE_SIZE, &observed);
        if (result)
            goto done;
        if (observed != a6_alias_original[page] ||
            observed != a6_cpu1_alias_data[2 * page][0]) {
            result = -ESTALE;
            goto done;
        }
    }
    for (page = 0; page < 2; page++) {
        for (phase = 0; phase < 2; phase++) {
            modified[page] = true;
            writel(a6_alias_patterns[page][phase], ram + page * PAGE_SIZE);
            dsb(sy);
            result = a6_alias_read_word(ram + page * PAGE_SIZE, &a6_alias_seen_ram[page][phase]);
            if (!result)
                result = a6_alias_read_word(zero + page * PAGE_SIZE, &a6_alias_seen_zero[page][phase]);
            if (!result && (a6_alias_seen_ram[page][phase] != a6_alias_patterns[page][phase] ||
                           a6_alias_seen_zero[page][phase] != a6_alias_patterns[page][phase]))
                result = -EIO;
            if (result)
                goto restore;
        }
    }
restore:
    for (page = 0; page < 2; page++) {
        if (!modified[page])
            continue;
        writel(a6_alias_original[page], ram + page * PAGE_SIZE);
        dsb(sy);
        error = a6_alias_read_word(ram + page * PAGE_SIZE, &a6_alias_restore_ram[page]);
        if (!error)
            error = a6_alias_read_word(zero + page * PAGE_SIZE, &a6_alias_restore_zero[page]);
        if (!error && (a6_alias_restore_ram[page] != a6_alias_original[page] ||
                       a6_alias_restore_zero[page] != a6_alias_original[page]))
            error = -EUCLEAN;
        if (error)
            result = error;
    }
done:
    if (ram)
        iounmap(ram);
    if (zero)
        iounmap(zero);
    a6_alias_write_result = result;
    pr_info("A6_CPU1_ALIAS_WRITE_V1 result=%d release_writes=0\n", result);
    for (page = 0; page < 2; page++)
        pr_info("a6-alias-write offset=%x original=%08x p0=%08x ram0=%08x zero0=%08x p1=%08x ram1=%08x zero1=%08x restore_ram=%08x restore_zero=%08x\n",
                (unsigned int)(page * PAGE_SIZE), a6_alias_original[page],
                a6_alias_patterns[page][0], a6_alias_seen_ram[page][0], a6_alias_seen_zero[page][0],
                a6_alias_patterns[page][1], a6_alias_seen_ram[page][1], a6_alias_seen_zero[page][1],
                a6_alias_restore_ram[page], a6_alias_restore_zero[page]);
}

static ssize_t a6_alias_write_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
    ssize_t used;
    unsigned int page;

    mutex_lock(&a6_cpu1_alias_lock);
    used = sysfs_emit(buf, "A6_CPU1_ALIAS_WRITE_V1 attempted=%u result=%d release_writes=0\n",
                      a6_alias_write_attempted, a6_alias_write_result);
    for (page = 0; page < 2; page++)
        used += sysfs_emit_at(buf, used,
            "offset=%x original=%08x pattern0=%08x ram0=%08x zero0=%08x pattern1=%08x ram1=%08x zero1=%08x restore_ram=%08x restore_zero=%08x\n",
            (unsigned int)(page * PAGE_SIZE), a6_alias_original[page],
            a6_alias_patterns[page][0], a6_alias_seen_ram[page][0], a6_alias_seen_zero[page][0],
            a6_alias_patterns[page][1], a6_alias_seen_ram[page][1], a6_alias_seen_zero[page][1],
            a6_alias_restore_ram[page], a6_alias_restore_zero[page]);
    mutex_unlock(&a6_cpu1_alias_lock);
    return used;
}

static ssize_t a6_alias_write_store(struct kobject *kobj, struct kobj_attribute *attr,
                                   const char *buf, size_t count)
{
    int result;

    if (a6_cpu1_release_writes)
        return -EBUSY;
    if (!sysfs_streq(buf, "prove"))
        return -EINVAL;
    mutex_lock(&a6_cpu1_alias_lock);
    if (a6_alias_write_attempted) {
        mutex_unlock(&a6_cpu1_alias_lock);
        return -EALREADY;
    }
    a6_alias_write_prove();
    result = a6_alias_write_result;
    mutex_unlock(&a6_cpu1_alias_lock);
    return result ? result : count;
}

static struct kobj_attribute a6_alias_write_attr =
    __ATTR(write_proof, 0600, a6_alias_write_show, a6_alias_write_store);

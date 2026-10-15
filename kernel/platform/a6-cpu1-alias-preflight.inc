// SPDX-License-Identifier: GPL-2.0-only
/* One read-only, fault-guarded physical-zero comparison on CPU0.
 * Both views use uncached device mappings. No vector or PMGR writes.
 */
#include <linux/fs.h>
#include <linux/mutex.h>
#include <linux/of_reserved_mem.h>
#include <linux/uaccess.h>

#define A6_ALIAS_PAGES 2
#define A6_ALIAS_WORDS (PAGE_SIZE / sizeof(u32))
static DEFINE_MUTEX(a6_cpu1_alias_lock);
static bool a6_cpu1_alias_sampled;
static int a6_cpu1_alias_result;
static unsigned int a6_cpu1_alias_words, a6_cpu1_alias_same[A6_ALIAS_PAGES];
static unsigned int a6_cpu1_alias_nonzero_mask;
/* Binary order: RAM[0], zero[0], RAM[0x1000], zero[0x1000]. */
static u32 a6_cpu1_alias_data[2 * A6_ALIAS_PAGES][A6_ALIAS_WORDS];

/* Called with the mutex held, in process context. No repeated hardware
 * reads after the first capture, including after a precise read fault.
 */
static void a6_cpu1_alias_sample(void)
{
    void __iomem *zero, *ram;
    unsigned int i, page, word;
    u32 *ram_word, *zero_word;

    if (a6_cpu1_alias_sampled)
        return;
    a6_cpu1_alias_sampled = true;
    ram = ioremap(0x80000000, A6_ALIAS_PAGES * PAGE_SIZE);
    zero = ioremap(0, A6_ALIAS_PAGES * PAGE_SIZE);
    if (!ram || !zero) {
        a6_cpu1_alias_result = -ENOMEM;
        goto done;
    }
    for (i = 0; i < A6_ALIAS_PAGES * A6_ALIAS_WORDS; i++) {
        page = i / A6_ALIAS_WORDS;
        word = i % A6_ALIAS_WORDS;
        ram_word = &a6_cpu1_alias_data[2 * page][word];
        zero_word = &a6_cpu1_alias_data[2 * page + 1][word];
        /* One aligned word per read. The exception table handles a
         * precise data abort; no bulk memory comparison.
         */
        a6_cpu1_alias_result = copy_from_kernel_nofault(ram_word,
            (const void __force *)(ram + i * sizeof(u32)), sizeof(u32));
        if (a6_cpu1_alias_result)
            break;
        a6_cpu1_alias_result = copy_from_kernel_nofault(zero_word,
            (const void __force *)(zero + i * sizeof(u32)), sizeof(u32));
        if (a6_cpu1_alias_result)
            break;
        a6_cpu1_alias_words++;
        if (*ram_word == *zero_word)
            a6_cpu1_alias_same[page]++;
        if (*ram_word)
            a6_cpu1_alias_nonzero_mask |= BIT(page);
    }
done:
    if (ram)
        iounmap(ram);
    if (zero)
        iounmap(zero);
    pr_info("A6_CPU1_ALIAS_V2 result=%d words=%u same0=%u same1000=%u nonzero_mask=%x uncached=1 release_writes=0\n",
        a6_cpu1_alias_result, a6_cpu1_alias_words, a6_cpu1_alias_same[0],
        a6_cpu1_alias_same[1], a6_cpu1_alias_nonzero_mask);
}

static ssize_t a6_cpu1_alias_show(struct kobject *kobj,
                                 struct kobj_attribute *attr, char *buf)
{
    ssize_t used;

    mutex_lock(&a6_cpu1_alias_lock);
    a6_cpu1_alias_sample();
    used = sysfs_emit(buf,
        "A6_CPU1_ALIAS_V2 result=%d words=%u same0=%u same1000=%u nonzero_mask=%x uncached=1 release_writes=0\n"
        "raw_bytes=%zu order=ram0,zero0,ram1000,zero1000 word_endian=little\n",
        a6_cpu1_alias_result, a6_cpu1_alias_words, a6_cpu1_alias_same[0],
        a6_cpu1_alias_same[1], a6_cpu1_alias_nonzero_mask,
        sizeof(a6_cpu1_alias_data));
    mutex_unlock(&a6_cpu1_alias_lock);
    return used;
}

static ssize_t a6_cpu1_alias_raw_read(struct file *file, struct kobject *kobj,
                                    const struct bin_attribute *attr,
                                    char *buf, loff_t offset, size_t count)
{
    ssize_t result;

    mutex_lock(&a6_cpu1_alias_lock);
    a6_cpu1_alias_sample();
    result = memory_read_from_buffer(buf, count, &offset,
                                    a6_cpu1_alias_data, sizeof(a6_cpu1_alias_data));
    mutex_unlock(&a6_cpu1_alias_lock);
    return result;
}

#ifdef A6_CPU1_ALIAS_WRITE
#include "a6-cpu1-alias-write.inc"
#endif
#ifdef A6_CPU1_ENTRY_PROBE
#include "a6-cpu1-entry-probe.inc"
#endif

static struct kobj_attribute a6_cpu1_alias_attr =
    __ATTR(snapshot, 0400, a6_cpu1_alias_show, NULL);
static struct attribute *a6_cpu1_alias_attrs[] = {
    &a6_cpu1_alias_attr.attr,
#ifdef A6_CPU1_ALIAS_WRITE
    &a6_alias_write_attr.attr,
#endif
#ifdef A6_CPU1_ENTRY_PROBE
    &a6_entry_attr.attr,
#if A6_ENTRY_IRQ_PA
    &a6_ipi_attr.attr,
#if A6_ENTRY_TLBI_PROBE
#if A6_ENTRY_CACHE_PROBE
    &a6_cache_attr.attr,
#else
    &a6_tlbi_attr.attr,
#endif
#endif
#endif
#endif
    NULL
};
static const struct bin_attribute a6_cpu1_alias_raw_attr = {
    .attr = { .name = "snapshot_raw", .mode = 0400 },
    .size = sizeof(a6_cpu1_alias_data), .read = a6_cpu1_alias_raw_read,
};
static const struct bin_attribute *const a6_cpu1_alias_bin_attrs[] = {
    &a6_cpu1_alias_raw_attr, NULL
};
static const struct attribute_group a6_cpu1_alias_group = {
    .name = "a6_cpu1_alias", .attrs = a6_cpu1_alias_attrs,
    .bin_attrs = a6_cpu1_alias_bin_attrs,
};

static bool __init a6_cpu1_alias_reserved(const char *path, phys_addr_t base,
                                       phys_addr_t size)
{
    struct device_node *node = of_find_node_by_path(path);
    struct reserved_mem *region;
    bool valid;

    if (!node)
        return false;
    region = of_reserved_mem_lookup(node);
    valid = region && region->base == base && region->size == size &&
            of_property_read_bool(node, "no-map");
    of_node_put(node);
    return valid;
}

static int __init a6_cpu1_alias_init(void)
{
    if (!of_machine_is_compatible("apple,n42ap") || PAGE_SIZE != 4096 ||
        PHYS_OFFSET != 0x80000000 ||
        !a6_cpu1_alias_reserved("/reserved-memory/a6-cpu1-reset-vector@80000000", 0x80000000, 0x2000) ||
#ifdef A6_CPU1_TLBI_PROBE
        !a6_cpu1_alias_reserved("/reserved-memory/a6-cpu1-tlbi-private@83ff6000", 0x83ff6000, 0x9000))
#else
        !a6_cpu1_alias_reserved("/reserved-memory/a6-cpu1-mailbox@83ffe000", 0x83ffe000, 0x1000))
#endif
        return -ENODEV;
    return sysfs_create_group(firmware_kobj, &a6_cpu1_alias_group);
}
late_initcall(a6_cpu1_alias_init);

/* Read-only copy of boot-time capture; never expose arbitrary physical reads. */
#include <linux/kobject.h>
#include <linux/sysfs.h>
static u32 a6_memory_capture_copy[0xb00 / 4];
static ssize_t a6_memory_capture_read(struct file *file, struct kobject *kobj,
        const struct bin_attribute *attr, char *buf, loff_t off, size_t count)
{
    if (off < 0 || off >= sizeof(a6_memory_capture_copy))
        return 0;
    count = min_t(size_t, count, sizeof(a6_memory_capture_copy) - off);
    memcpy(buf, (char *)a6_memory_capture_copy + off, count);
    return count;
}
static const struct bin_attribute a6_memory_capture_attr = {
    .attr = { .name = "a6_memory_capture", .mode = 0400 },
    .size = sizeof(a6_memory_capture_copy),
    .read = a6_memory_capture_read,
};
static bool a6_memory_capture_mapping_valid(void)
{
    unsigned long address = 0x83fff000UL;
    pgd_t *pgd = pgd_offset_k(address);
    p4d_t *p4d = p4d_offset(pgd, address);
    pud_t *pud = pud_offset(p4d, address);
    pmd_t *pmd = pmd_offset(pud, address);
    u32 value = pmd_val(pmd[(address >> SECTION_SHIFT) & 1]);
    /* Reuse the scratch mapping created by head.S. Its attributes come from
     * PROCINFO_MM_MMUFLAGS, unlike the framebuffer's IO attributes. Do not
     * create a second alias or impose the framebuffer's attribute test.
     */
    return (value & PMD_TYPE_MASK) == PMD_TYPE_SECT &&
           (value & SECTION_MASK) == (address & SECTION_MASK);
}
static int __init a6_memory_capture_init(void)
{
    unsigned int i;
    int error;
    if (!of_machine_is_compatible("apple,n42ap") ||
        !a6_memory_capture_mapping_valid())
        return -EINVAL;
    for (i = 0; i < ARRAY_SIZE(a6_memory_capture_copy); i++)
        a6_memory_capture_copy[i] = readl((void __iomem *)(0x83fff100UL + i * 4));
    if (a6_memory_capture_copy[0] != 0x41364d31 ||
        a6_memory_capture_copy[5] > 36)
        return -EINVAL;
    error = sysfs_create_bin_file(firmware_kobj, &a6_memory_capture_attr);
    pr_info("a6-memory: capture status=%u records=%u flags=%u export=%d\n",
            a6_memory_capture_copy[1], a6_memory_capture_copy[5],
            a6_memory_capture_copy[7], error);
    return error;
}
late_initcall(a6_memory_capture_init);

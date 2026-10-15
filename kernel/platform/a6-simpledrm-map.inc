/* SPDX-License-Identifier: GPL-2.0-only */
/* Reuse A6's permanent strongly-ordered framebuffer mapping; never WC alias. */
#include <asm/pgtable.h>
static bool a6_drm_mapping_valid(unsigned long base, unsigned long size)
{
    unsigned long address;

    for (address = base & SECTION_MASK; address < base + size;
         address += SECTION_SIZE) {
        pgd_t *pgd = pgd_offset_k(address);
        p4d_t *p4d = p4d_offset(pgd, address);
        pud_t *pud = pud_offset(p4d, address);
        pmd_t *pmd = pmd_offset(pud, address);
        /* ARM short-descriptor Linux PMDs contain two 1 MiB sections. */
        u32 value = pmd_val(pmd[(address >> SECTION_SHIFT) & 1]);

        if ((value & PMD_TYPE_MASK) != PMD_TYPE_SECT ||
            (value & SECTION_MASK) != address ||
            (value & (PMD_SECT_TEX(7) | PMD_SECT_CACHEABLE |
                      PMD_SECT_BUFFERABLE)))
            return false;
    }
    return true;
}


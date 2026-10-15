// SPDX-License-Identifier: GPL-2.0-only
/* CPU0's only cached view of the private test page. Called before CPU1 release. */
#include <asm/io.h>
#include <asm/pgtable.h>
#include <asm/tlbflush.h>
#include <linux/pgtable.h>

#define A6_CACHE_DATA_PA 0x83ff6000
#define A6_CACHE_ATTR_MASK (0x1c0 | 0x400 | 0x0c)
#define A6_CACHE_WB_ATTR 0x0c /* TEX=0, C=B=1, S=0 */
#define A6_CACHE_WA_ATTR 0x4c /* TEX=1, C=B=1, S=0 */

static void *a6_cache_cpu0_view;
static u32 a6_cache_cpu0_hw_pte, a6_cache_cpu0_sctlr, a6_cache_cpu1_pte;
static u32 a6_cache_cpu0_prrr, a6_cache_cpu0_nmrr;

static int a6_cache_cpu0_map(void)
{
    unsigned long va;
    pmd_t *pmd;
    pte_t *pte;
    void __iomem *cpu1_l2;
    u32 attributes, cpu1_pte;
    u32 hw;
    int error = -EPROTO;

    a6_cache_cpu0_sctlr = get_cr();
#ifdef A6_CPU1_CACHE_TRE_PROBE
    if (!(a6_cache_cpu0_sctlr & CR_TRE))
        return -EOPNOTSUPP;
    asm volatile("mrc p15, 0, %0, c10, c2, 0" : "=r" (a6_cache_cpu0_prrr));
    asm volatile("mrc p15, 0, %0, c10, c2, 1" : "=r" (a6_cache_cpu0_nmrr));
    if (a6_cache_cpu0_prrr != 0xff0a81a8 ||
        a6_cache_cpu0_nmrr != 0x40e040e0)
        return -EOPNOTSUPP;
#else
    if (a6_cache_cpu0_sctlr & CR_TRE)
        return -EOPNOTSUPP;
#endif
    a6_cache_cpu0_view = arch_memremap_wb(A6_CACHE_DATA_PA, PAGE_SIZE, 0);
    if (!a6_cache_cpu0_view)
        return -ENOMEM;
    va = (unsigned long)a6_cache_cpu0_view;
    pmd = pmd_off_k(va);
    if (!pmd || pmd_none(*pmd) || pmd_leaf(*pmd))
        goto unmap;
    pte = pte_offset_kernel(pmd, va);
    if (!pte)
        goto unmap;
    /* ARM short-descriptor PTEs keep the hardware half 512 words after
     * Linux's software half. Check the actual entry used by the MMU.
     */
    hw = pte_val(READ_ONCE(pte[PTE_HWTABLE_PTRS]));
#ifdef A6_CPU1_CACHE_SHAREABLE_PROBE
    /* The UP kernel's MT_MEMORY_RW mapping is S=0. This one reserved,
     * no-map test page is the only cached alias, and CPU1 is still off.
     * Change both Linux and hardware PTEs through the ARM helper before
     * either CPU reads data, flush CPU0's old translation, then read back.
     */
    if (hw != 0x83ff601f || (pte_val(READ_ONCE(*pte)) & L_PTE_SHARED))
        goto unmap;
    set_pte_ext(pte, __pte(pte_val(READ_ONCE(*pte)) | L_PTE_SHARED), 0);
    dsb(sy);
    flush_tlb_kernel_range(va, va + PAGE_SIZE);
    dsb(sy);
    isb();
    hw = pte_val(READ_ONCE(pte[PTE_HWTABLE_PTRS]));
    if (hw != 0x83ff641f ||
        !(pte_val(READ_ONCE(*pte)) & L_PTE_SHARED))
        goto unmap;
#endif
    a6_cache_cpu0_hw_pte = hw;
    attributes = hw & A6_CACHE_ATTR_MASK;
    /* MT_MEMORY_RW is XN on CPU0, so its small-page type may be 0b11.
     * CPU1's read-only diagnostic PTE may remain executable (0b10).
     */
    if ((hw & PAGE_MASK) != A6_CACHE_DATA_PA ||
        (hw & 0x2) != 0x2 ||
#ifdef A6_CPU1_CACHE_SHAREABLE_PROBE
        (attributes != (A6_CACHE_WB_ATTR | PTE_EXT_SHARED) &&
         attributes != (A6_CACHE_WA_ATTR | PTE_EXT_SHARED)))
#else
        (attributes != A6_CACHE_WB_ATTR && attributes != A6_CACHE_WA_ATTR))
#endif
        goto unmap;
    /* CPU1 is not released yet. Match exactly the CPU0 TEX/C/B/S policy,
     * and verify the private table write before any vector is installed.
     */
    cpu1_pte = A6_TLBI_PTE_A | (attributes & (0x40 | PTE_EXT_SHARED));
    cpu1_l2 = ioremap(A6_TLBI_L2_PA, PAGE_SIZE);
    if (!cpu1_l2) {
        error = -ENOMEM;
        goto unmap;
    }
    writel(cpu1_pte, cpu1_l2);
    dsb(sy);
    if (readl(cpu1_l2) != cpu1_pte) {
        error = -EIO;
        iounmap(cpu1_l2);
        goto unmap;
    }
    a6_cache_cpu1_pte = cpu1_pte;
    iounmap(cpu1_l2);
    return 0;

unmap:
    iounmap((void __iomem *)a6_cache_cpu0_view);
    a6_cache_cpu0_view = NULL;
    return error;
}

/* Read-only snapshot for the observed BusyBox store, ARM non-LPAE only.
 * Follow show_pte's folded page-table walk; never alter PTEs or issue TLBI.
 */
#ifdef CONFIG_ARM_LPAE
#error A6 PTE proof requires two-level page tables
#endif
extern void a6_shell_pte_report(unsigned int, unsigned int, unsigned int,
    unsigned int, unsigned int, unsigned int, unsigned int, unsigned int, unsigned int);
static unsigned int a6_pte_hits;
static void a6_pte_snapshot(unsigned long addr, unsigned int phase, unsigned int hit)
{
    struct mm_struct *mm = current->mm;
    pgd_t *pgd;
    p4d_t *p4d;
    pud_t *pud;
    pmd_t *pmd;
    pte_t *pte;
    spinlock_t *ptl;
    unsigned int sw = 0xffffffff, hw = 0xffffffff, pm = 0xffffffff;
    unsigned int ttbr, cid, dacr, sctlr;
    if (!mm) goto report;
    pgd = pgd_offset(mm, addr);
    p4d = p4d_offset(pgd, addr);
    if (p4d_none(*p4d) || p4d_bad(*p4d)) goto report;
    pud = pud_offset(p4d, addr);
    if (pud_none(*pud) || pud_bad(*pud)) goto report;
    pmd = pmd_offset(pud, addr);
    pm = pmd_val(pmd[(addr >> SECTION_SHIFT) & 1]);
    if (pmd_none(*pmd) || pmd_bad(*pmd)) goto report;
    if (PageHighMem(pfn_to_page(pmd_val(*pmd) >> PAGE_SHIFT))) goto report;
    pte = pte_offset_map_lock(mm, pmd, addr, &ptl);
    if (!pte) goto report;
    sw = pte_val(READ_ONCE(*pte));
    hw = pte_val(READ_ONCE(pte[PTE_HWTABLE_PTRS]));
    pte_unmap_unlock(pte, ptl);
report:
    asm volatile("mrc p15, 0, %0, c2, c0, 0" : "=r" (ttbr));
    asm volatile("mrc p15, 0, %0, c13, c0, 1" : "=r" (cid));
    asm volatile("mrc p15, 0, %0, c3, c0, 0" : "=r" (dacr));
    asm volatile("mrc p15, 0, %0, c1, c0, 0" : "=r" (sctlr));
    a6_shell_pte_report(phase, hit, sw, hw, pm, ttbr, cid, dacr, sctlr);
}

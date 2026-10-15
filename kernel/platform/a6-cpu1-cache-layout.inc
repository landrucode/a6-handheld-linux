// SPDX-License-Identifier: GPL-2.0-only
/* CPU1-only cache experiment. Test data has no CPU1 identity alias. */
#include "a6-cpu1-tlbi-blob.inc"

#define A6_TLBI_L1_PA 0x83ff8000
#define A6_TLBI_L2_PA 0x83ffc000
#define A6_TLBI_DATA_A_PA 0x83ff6000
#define A6_TLBI_DATA_B_PA 0x83ff7000
#define A6_TLBI_TEST_VA 0xc0000000
#define A6_TLBI_A_VALUE 0xa6a60011
#define A6_TLBI_B_VALUE 0xb6b60022
#define A6_TLBI_PTE_A 0x83ff683e
#define A6_TLBI_PTE_B 0x83ff783e
#ifdef A6_CPU1_CACHE_TRE_PROBE
/* Pinned proc-v7-2level.S PRRR/NMRR: index 1 is Normal NC;
 * index 4 is Device. These replace the non-remapped encodings.
 */
#define A6_CACHE_PRIVATE_NC_PTE 0x36
#define A6_CACHE_AIC_SECTION 0x3f211c12
#else
#define A6_CACHE_PRIVATE_NC_PTE 0x72
#define A6_CACHE_AIC_SECTION 0x3f200c06
#endif

static int a6_tlbi_install(void)
{
    void __iomem *l1 = NULL, *l2 = NULL, *a = NULL, *b = NULL, *code = NULL;
    unsigned int i;
    u32 expected;
    int result = -ENOMEM;

    l1 = ioremap(A6_TLBI_L1_PA, 0x4000);
    l2 = ioremap(A6_TLBI_L2_PA, 0x1000);
    a = ioremap(A6_TLBI_DATA_A_PA, 0x1000);
    b = ioremap(A6_TLBI_DATA_B_PA, 0x1000);
    code = ioremap(0x83ffd000, 0x1000);
    if (!l1 || !l2 || !a || !b || !code)
        goto out;
    writel(A6_TLBI_A_VALUE, a);
    writel(A6_TLBI_B_VALUE, b);
    if (readl(a) != A6_TLBI_A_VALUE || readl(b) != A6_TLBI_B_VALUE) {
        result = -EIO;
        goto out;
    }
    for (i = 0; i < 4096; i++)
        writel(i == 0 ? 0x83ffc801 : i == 0x3f2 ? A6_CACHE_AIC_SECTION :
               i == 0x83f ? 0x83ffc401 : i == 0xc00 ? 0x83ffc001 : 0,
               l1 + i * 4);
    for (i = 0; i < 768; i++) {
        expected = i == 0 ? A6_TLBI_PTE_A :
                   i >= 256 + 0xf8 && i <= 256 + 0xfe ?
                       0x83f00000 + (i - 256) * 0x1000 + A6_CACHE_PRIVATE_NC_PTE :
                   i == 512 ? 0x80000000 + A6_CACHE_PRIVATE_NC_PTE :
                   i == 513 ? 0x80001000 + A6_CACHE_PRIVATE_NC_PTE : 0;
        writel(expected, l2 + i * 4);
    }
    for (i = 0; i < ARRAY_SIZE(a6_tlbi_blob); i++)
        writel(a6_tlbi_blob[i], code + i * 4);
    dsb(sy);
    result = -EIO;
    for (i = 0; i < 4096; i++) {
        expected = i == 0 ? 0x83ffc801 : i == 0x3f2 ? A6_CACHE_AIC_SECTION :
                   i == 0x83f ? 0x83ffc401 : i == 0xc00 ? 0x83ffc001 : 0;
        if (readl(l1 + i * 4) != expected)
            goto out;
    }
    for (i = 0; i < 768; i++) {
        expected = i == 0 ? A6_TLBI_PTE_A :
                   i >= 256 + 0xf8 && i <= 256 + 0xfe ?
                       0x83f00000 + (i - 256) * 0x1000 + A6_CACHE_PRIVATE_NC_PTE :
                   i == 512 ? 0x80000000 + A6_CACHE_PRIVATE_NC_PTE :
                   i == 513 ? 0x80001000 + A6_CACHE_PRIVATE_NC_PTE : 0;
        if (readl(l2 + i * 4) != expected)
            goto out;
    }
    for (i = 0; i < ARRAY_SIZE(a6_tlbi_blob); i++) {
        if (readl(code + i * 4) != a6_tlbi_blob[i])
            goto out;
    }
    result = 0;
out:
    if (code)
        iounmap(code);
    if (b)
        iounmap(b);
    if (a)
        iounmap(a);
    if (l2)
        iounmap(l2);
    if (l1)
        iounmap(l1);
    return result;
}

#!/usr/bin/env python3
"""Apply the compile-only A6 software shootdown candidate to staged sources."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
header = root / "arch/arm/include/asm/tlbflush.h"
platform = root / "arch/arm/include/asm/smp_plat.h"
assembly = root / "arch/arm/mm/tlb-v7.S"

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"expected one anchor: {old!r}")
    return text.replace(old, new)

h = header.read_text()
h = replace_once(h, "#define v7wbi_tlb_flags_smp\t(TLB_WB | TLB_BARRIER)",
                 "#define v7wbi_tlb_flags_smp\t(TLB_WB | TLB_BARRIER | "
                 "TLB_V6_U_FULL | TLB_V6_U_PAGE | TLB_V6_U_ASID)")
p = platform.read_text()
p = replace_once(p, "return ((read_cpuid_ext(CPUID_EXT_MMFR3) >> 12) & 0xf) < 2;",
                 "/* A6 candidate: remote invalidation requires acknowledged IPIs. */\n"
                 "\treturn 1;")
a = assembly.read_text()
# Remove the erratum alternatives too: every range operation is local in
# this isolated Swift build. Software broadcast selects the target CPUs.
old = """#ifdef CONFIG_ARM_ERRATA_720789
\tALT_SMP(mcr\tp15, 0, r0, c8, c3, 3)\t@ TLB invalidate U MVA all ASID (shareable)
#else
\tALT_SMP(mcr\tp15, 0, r0, c8, c3, 1)\t@ TLB invalidate U MVA (shareable)
#endif
\tALT_UP(mcr\tp15, 0, r0, c8, c7, 1)\t@ TLB invalidate U MVA"""
if a.count(old) != 2:
    raise SystemExit("expected two stock range loops")
a = a.replace(old, "\tmcr\tp15, 0, r0, c8, c7, 1\t@ A6 local TLBI; IPI broadcast above")
# Validate all anchors before changing any file.
header.write_text(h)
platform.write_text(p)
assembly.write_text(a)
print("A6 compile-only TLBI: software broadcast + local full/page/ASID/range")

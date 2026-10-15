#!/usr/bin/env python3
"""Isolate full local TLBI at ASID rollover; leave early-boot bypasses alone."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()
old = '\t\tlocal_flush_tlb_all();'
new = '''
        /* A6 proof: pending is set by flush_context on ASID rollover.
         * cpu_asid_lock holds IRQs disabled here. Preserve ordinary ordering;
         * test only the normal local unified full invalidation opcode.
         * Early boot and other full-flush callers remain unchanged.
         */
        pr_info("A6 ROLLOVER TLBI ENTER generation=%llx\\n",
                (unsigned long long)atomic64_read(&asid_generation));
        dsb(nshst);
        asm volatile("mcr p15, 0, %0, c8, c7, 0" : : "r" (0) : "memory");
        dsb(nsh);
        isb();
        pr_info("A6 ROLLOVER TLBI RETURN generation=%llx\\n",
                (unsigned long long)atomic64_read(&asid_generation));'''
if len(sys.argv) > 2 and sys.argv[2] == '1':
    begin = new.index('        dsb(nshst);')
    end = new.index('        pr_info("A6 ROLLOVER TLBI RETURN')
    new = new[:begin] + '        local_flush_tlb_all();\n' + new[end:]
    new = new.replace('test only the normal local unified full invalidation opcode.',
                      'use normal local_flush_tlb_all with TLB_V6_U_FULL restored.')
    new = new.replace('Early boot and other full-flush callers remain unchanged.',
                      'Other normal full-flush callers now also use the restored flag.')
if source.count(old) != 1:
    raise SystemExit('expected exactly one pending full flush in ARM context.c')
if len(sys.argv) > 3 and sys.argv[3] == '1':
    # The ASID lock is held with IRQs disabled. Keep the messages in the ring
    # buffer, but defer console delivery rather than invoke console drivers
    # from this lock context. This changes instrumentation, not maintenance.
    if new.count('pr_info(') != 2:
        raise SystemExit('expected exactly two rollover log sites')
    new = new.replace('pr_info(', 'printk_deferred(KERN_INFO ')
path.write_text(source.replace(old, new))

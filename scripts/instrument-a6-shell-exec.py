#!/usr/bin/env python3
"""Separate userspace exec attempts from the already-proven kernel /init exec."""
from pathlib import Path
import os
import sys

repo, linux = map(Path, sys.argv[1:])
head = linux / 'arch/arm/kernel/head.S'
s = head.read_text()
assert s.count('a6_exec_seen: .word 0') == 1
head.write_text(s.replace('a6_exec_seen: .word 0', '.global a6_exec_seen\na6_exec_seen: .word 0'))
p = linux / 'fs/exec.c'
s = p.read_text()

def section(start, end, pairs):
    global s
    a = s.index(start)
    b = s.index(end, a)
    block = s[a:b]
    for old, new in pairs:
        assert block.count(old) == 1, old
        block = block.replace(old, new, 1)
    s = s[:a] + block + s[b:]

def around(statement, label):
    return statement, (f'\ta6_diag_timer_row(1, "{label + " ENTER":25s}");\n' + statement +
                       f'\n\ta6_diag_timer_row(1, "{label + " RETURN":25s}");\n'
                       '\ta6_shell_value(2, "RETURN ", retval);')

section('static int do_execveat_common(', '\nint kernel_execve(', [
    ('\tint retval;\n', '\tint retval;\n\ta6_shell_exec_begin();\n'),
    around('\tretval = count(argv, MAX_ARG_STRINGS);', 'COUNT ARGV'),
    around('\tretval = count(envp, MAX_ARG_STRINGS);', 'COUNT ENVP'),
    around('\tretval = bprm_stack_limits(bprm);', 'STACK LIMITS'),
    around('\tretval = copy_string_kernel(bprm->filename, bprm);', 'COPY FILENAME'),
    around('\tretval = copy_strings(bprm->envc, envp, bprm);', 'COPY USER ENVP'),
    around('\tretval = copy_strings(bprm->argc, argv, bprm);', 'COPY USER ARGV'),
    ('\treturn bprm_execve(bprm);', '\ta6_diag_timer_row(1, "BPRM EXEC ENTER          ");\n'
     '\tretval = bprm_execve(bprm);\n'
     '\ta6_diag_timer_row(1, "BPRM EXEC RETURN         ");\n'
     '\ta6_shell_value(2, "RETURN ", retval);\n\treturn retval;'),
])
inner = [
    ('\t\tstr = get_user_arg_ptr(argv, argc);', 'USER POINTER'),
    ('\t\tlen = strnlen_user(str, MAX_ARG_STRLEN);', 'USER STRNLEN'),
    ('\t\t\tcond_resched();', 'USER RESCHED'),
    ('\t\t\t\tpage = get_arg_page(bprm, pos, 1);', 'USER ARG PAGE'),
    ('\t\t\t\tflush_arg_page(bprm, kpos, kmapped_page);', 'USER ARG FLUSH'),
]
pairs = []
for statement, label in inner:
    pairs.append((statement, f'\ta6_diag_timer_row(23, "{label + " ENTER":25s}");\n' + statement +
                  f'\n\ta6_diag_timer_row(23, "{label + " RETURN":25s}");'))
pairs += [
    ('\t\t\tif (copy_from_user(kaddr+offset, str, bytes_to_copy)) {',
     '\t\t\ta6_diag_timer_row(23, "USER COPY ENTER          ");\n'
     '\t\t\tif (copy_from_user(kaddr+offset, str, bytes_to_copy)) {'),
    ('\treturn ret;', '\ta6_diag_timer_row(23, "USER COPY RETURN         ");\n\treturn ret;'),
]
section('static int copy_strings(', '\nint copy_string_kernel(', pairs)
prefix = '''extern void a6_diag_timer_row(unsigned int, const char *);
extern unsigned int a6_exec_seen;
static unsigned int a6_shell_exec_count;
static void a6_shell_value(unsigned int row, const char *prefix, unsigned int value)
{
    char line[26];
    unsigned int i = 0, j;
    while (prefix[i] && i < 16) { line[i] = prefix[i]; i++; }
    for (j = 0; j < 8; j++)
        line[i++] = "0123456789ABCDEF"[(value >> (28 - j * 4)) & 15];
    while (i < 25) line[i++] = ' ';
    line[25] = 0;
    a6_diag_timer_row(row, line);
}
static void a6_shell_exec_begin(void)
{
    unsigned int row;
    for (row = 0; row < 24; row++)
        a6_diag_timer_row(row, "                         ");
    a6_exec_seen = 0;
    a6_shell_value(0, "USER EXEC ", ++a6_shell_exec_count);
}
'''
p.write_text(prefix + s)
if os.environ.get('A6_SHELL_FAULT_TRACE') == '1':
    # Observe faults only after a user exec, and only user-mode aborts.
    # Do not change mappings, retry policy, or handler return values.
    p.write_text(p.read_text() + '''
static unsigned int a6_shell_fault_count;
void a6_shell_fault_enter(unsigned int, unsigned int, unsigned int, unsigned int);
void a6_shell_fault_return(unsigned int);
void a6_shell_fault_enter(unsigned int kind, unsigned int pc,
                         unsigned int addr, unsigned int status)
{
    if (!a6_shell_exec_count) return;
    a6_diag_timer_row(1, kind ? "USER PREFETCH ABORT      " : "USER DATA ABORT          ");
    a6_shell_value(2, "FAULT COUNT ", ++a6_shell_fault_count);
    a6_diag_timer_row(20, "FAULT HANDLER ENTER      ");
    a6_shell_value(21, "PC ", pc);
    a6_shell_value(22, "ADDRESS ", addr);
    a6_shell_value(23, "FSR ", status);
}
void a6_shell_fault_return(unsigned int result)
{
    if (a6_shell_exec_count) a6_shell_value(20, "FAULT RETURN ", result);
}
''')
    fault = linux / 'arch/arm/mm/fault.c'
    t = fault.read_text()
    for kind, name, status, table, flags in [
        (0, 'do_DataAbort', 'fsr', 'fsr_info', 'fsr & ~FSR_LNX_PF'),
        (1, 'do_PrefetchAbort', 'ifsr', 'ifsr_info', 'ifsr | FSR_LNX_PF'),
    ]:
        old = (f'\tconst struct fsr_info *inf = {table} + fsr_fs({status});\n\n'
               f'\tif (!inf->fn(addr, {flags}, regs))\n\t\treturn;')
        new = (f'\tconst struct fsr_info *inf = {table} + fsr_fs({status});\n'
               '\tint a6_result;\n'
               f'\tif (user_mode(regs)) a6_shell_fault_enter({kind}, regs->ARM_pc, addr, {status});\n'
               f'\ta6_result = inf->fn(addr, {flags}, regs);\n'
               '\tif (user_mode(regs)) a6_shell_fault_return(a6_result);\n'
               '\tif (!a6_result)\n\t\treturn;')
        assert t.count(old) == 1, name
        t = t.replace(old, new, 1)
    fault.write_text('extern void a6_shell_fault_enter(unsigned int, unsigned int, unsigned int, unsigned int);\n'
                     'extern void a6_shell_fault_return(unsigned int);\n' + t)
if os.environ.get('A6_SHELL_PTE_TRACE') == '1':
    p.write_text(p.read_text() + '''
void a6_shell_pte_report(unsigned int, unsigned int, unsigned int, unsigned int,
                         unsigned int, unsigned int, unsigned int, unsigned int, unsigned int);
void a6_shell_pte_report(unsigned int phase, unsigned int hit, unsigned int sw,
                         unsigned int hw, unsigned int pmd, unsigned int ttbr,
                         unsigned int cid, unsigned int dacr, unsigned int sctlr)
{
    unsigned int row = (hit == 1 ? 4 : 10) + phase * 3;
    a6_shell_value(row, phase ? "POST SW " : "PRE SW ", sw);
    a6_shell_value(row + 1, phase ? "POST HW " : "PRE HW ", hw);
    a6_shell_value(row + 2, phase ? "POST PMD " : "PRE PMD ", pmd);
    a6_shell_value(16, "TTBR0 ", ttbr);
    a6_shell_value(17, "CONTEXTID ", cid);
    a6_shell_value(18, "DACR ", dacr);
    a6_shell_value(19, "SCTLR ", sctlr);
}
''')
    fault = linux / 'arch/arm/mm/fault.c'
    t = fault.read_text()
    helper = (repo / 'kernel/platform/a6-shell-pte-trace.inc').read_text()
    anchor = 'void show_pte(const char *lvl, struct mm_struct *mm, unsigned long addr)'
    assert t.count(anchor) == 2
    t = t.replace(anchor, helper + '\n' + anchor, 1)
    anchor = '\tint a6_result;\n\tif (user_mode(regs)) a6_shell_fault_enter(0,'
    assert t.count(anchor) == 1
    t = t.replace(anchor, '\tint a6_result;\n'
                  '\tunsigned int a6_hit = 0;\n'
                  '\tif (user_mode(regs) && regs->ARM_pc == 0xda06c && addr == 0x1d2aec) {\n'
                  '\t\ta6_hit = ++a6_pte_hits;\n'
                  '\t\ta6_pte_snapshot(addr, 0, a6_hit);\n\t}\n'
                  '\tif (user_mode(regs)) a6_shell_fault_enter(0,', 1)
    anchor = '\ta6_result = inf->fn(addr, fsr & ~FSR_LNX_PF, regs);'
    assert t.count(anchor) == 1
    t = t.replace(anchor, anchor + '\n\tif (a6_hit) a6_pte_snapshot(addr, 1, a6_hit);', 1)
    fault.write_text(t)
if os.environ.get('A6_SHELL_TLBI_PROOF') == '1':
    fault = linux / 'arch/arm/mm/fault.c'
    t = fault.read_text()
    helper = '''
extern void a6_diag_timer_row(unsigned int, const char *);
static noinline void a6_target_page_tlbi(unsigned long addr)
{
    unsigned long flags;
    unsigned int cid, operand;
    local_irq_save(flags);
    asm volatile("mrc p15, 0, %0, c13, c0, 1" : "=r" (cid));
    operand = (addr & PAGE_MASK) | (cid & 0xff);
    a6_diag_timer_row(3, "ONE PAGE TLBI ENTER      ");
    asm volatile("dsb sy\\n\\tmcr p15, 0, %0, c8, c7, 1\\n\\tdsb sy\\n\\tisb"
                 : : "r" (operand) : "memory");
    a6_diag_timer_row(3, "ONE PAGE TLBI RETURN     ");
    local_irq_restore(flags);
}
'''
    anchor = 'static unsigned int a6_pte_hits;'
    assert t.count(anchor) == 1
    t = t.replace(anchor, helper + '\n' + anchor, 1)
    anchor = '\tif (a6_hit) a6_pte_snapshot(addr, 1, a6_hit);'
    assert t.count(anchor) == 1
    t = t.replace(anchor, anchor + '\n'
                  '\tif (a6_hit == 1 && a6_result == 0 && fsr == 0x80f)\n'
                  '\t\ta6_target_page_tlbi(addr);', 1)
    fault.write_text(t)

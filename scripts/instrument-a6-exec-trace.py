#!/usr/bin/env python3
"""Once-only readable exec checkpoints, reusing register-preserving hooks."""
from pathlib import Path
import re
import sys
repo, linux = map(Path, sys.argv[1:])
stages = [
    ("a6_run_init_enter", "RUN INIT ENTER"),
    ("a6_run_init_logged", "RUN INIT LOGGED"),
    ("a6_kernel_exec_enter", "KERNEL EXEC ENTER"),
    ("a6_exec_bprm", "BPRM EXEC"),
    ("a6_exec_handler", "BINARY HANDLER"),
    ("a6_elf_enter", "ELF ENTER"),
    ("a6_elf_headers", "ELF HEADERS"),
    ("a6_exec_begin", "BEGIN NEW EXEC"),
    ("a6_exec_mmap_pre", "EXEC MMAP ENTER"),
    ("a6_exec_mmap_ok", "EXEC MMAP RETURN"),
    ("a6_exec_ns_ok", "NAMESPACES RETURN"),
    ("a6_exec_sig_ok", "SIGHAND RETURN"),
    ("a6_exec_thr_ok", "THREAD FLUSHED"),
    ("a6_exec_perf_ok", "PERF RETURN"),
    ("a6_exec_cred_ok", "CREDS COMMITTED"),
    ("a6_exec_done", "BEGIN EXEC DONE"),
    ("a6_elf_stack", "ELF STACK READY"),
    ("a6_elf_mapped", "ELF SEGMENTS MAPPED"),
    ("a6_elf_tables", "ELF TABLES READY"),
    ("a6_elf_regs", "USER REGS PREPARED"),
    ("a6_user_return", "RETURN TO USER"),
    ("a6_user_svc", "FIRST USER SVC"),
    ("a6_kinit_fail", "EXEC RETURN ERROR"),
]
def replace(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new, 1)
head = linux / "arch/arm/kernel/head.S"
s = head.read_text()
for i, (name, label) in enumerate(stages[3:], 3):
    s, n = re.subn(r"^a6_(?:c|visible|quick)_stage " + name + r",[^\n]*$",
                  f"a6_boot_hook {name}, {96+i}", s, flags=re.M)
    assert n == 1, name
s += '\n.pushsection .text, "ax", %progbits\n.thumb\n'
for i, (name, label) in enumerate(stages[:3]):
    s += f"a6_boot_hook {name}, {96+i}\n"
s += ".popsection\n"
# These C-callable diagnostics (including disabled BX LR stubs) can run
# after free_initmem sets everything below _stext non-executable. Keep
# their definitions in permanent text, not head.S's current .head.text.
s = re.sub(r"^(a6_(?:boot_hook|c_stage|visible_stage|quick_stage) [^\n]+)$",
           lambda m: '.pushsection .text, "ax", %progbits\n' + m[1] + '\n.popsection',
           s, flags=re.M)
s = replace(s, "a6_boot_draw:\n", """a6_boot_draw:
    cmp r0, #96
    blo 13f
    sub r0, r0, #96
    cmp r0, #23
    bhs 9f
    ldr r1, =a6_exec_seen
    ldr r2, [r1]
    mov r3, #1
    lsl r3, r3, r0
    tst r2, r3
    bne 9f
    orr r2, r2, r3
    str r2, [r1]
    ldr r1, =a6_exec_labels
    ldr r7, [r1, r0, lsl #2]
    b 11f
13:
""")
s += '\n.pushsection .data, "aw", %progbits\n.balign 4\na6_exec_seen: .word 0\n'
s += 'a6_exec_hooks: .word ' + ','.join(name for name, _ in stages) + '\n'
s += 'a6_exec_labels: .word ' + ','.join(f'a6_exec_label_{i}' for i in range(len(stages))) + '\n'
for i, (_, label) in enumerate(stages):
    label = f"E{i:02d} {label}"
    assert len(label) <= 25
    s += f'a6_exec_label_{i}: .asciz "{label:25s}"\n'
s += '.popsection\n'
head.write_text(s)
p = linux / "init/main.c"
s = p.read_text()
s = replace(s, '\targv_init[0] = init_filename;', '\ta6_run_init_enter();\n\targv_init[0] = init_filename;')
s = replace(s, '\treturn kernel_execve(init_filename, argv_init, envp_init);',
            '\ta6_run_init_logged();\n\treturn kernel_execve(init_filename, argv_init, envp_init);')
p.write_text('extern void a6_run_init_enter(void);\nextern void a6_run_init_logged(void);\n' + s)
p = linux / "fs/exec.c"
s = replace(p.read_text(), '\t/* It is non-sense for kernel threads to call execve */',
            '\ta6_kernel_exec_enter();\n\t/* It is non-sense for kernel threads to call execve */')
p.write_text('extern void a6_kernel_exec_enter(void);\n' + s)

#!/usr/bin/env python3
"""Locate preparation before bprm_execve; guarded edits to temporary exec.c."""
from pathlib import Path
import sys
repo, linux = map(Path, sys.argv[1:])
p = linux / 'fs/exec.c'
s = p.read_text()

def mark(n, label):
    label = f'K{n:02d} {label}'
    assert len(label) <= 25, label
    return f'\ta6_exec_prep_mark("{label:25s}");\n'

def section(start, end, pairs):
    global s
    assert s.count(start) == 1 and s.count(end) == 1
    a, b = s.index(start), s.index(end, s.index(start))
    block = s[a:b]
    for old, new in pairs:
        assert block.count(old) == 1, (start, old)
        block = block.replace(old, new, 1)
    s = s[:a] + block + s[b:]

def surround(old, before, after):
    return old, mark(*before) + old + '\n' + mark(*after)

section('int kernel_execve(', '\nvoid set_binfmt(', [
    ('\ta6_kernel_exec_enter();', '\ta6_kernel_exec_enter();\n\ta6_exec_prep_active = 1;\n' + mark(0, 'KERNEL PREP ENTER')),
    surround('\tCLASS(filename_kernel, filename)(kernel_filename);', (1, 'FILENAME ENTER'), (2, 'FILENAME RETURN')),
    surround('\tCLASS(bprm, bprm)(AT_FDCWD, filename, 0);', (3, 'BINPRM ALLOC ENTER'), (4, 'BINPRM ALLOC RETURN')),
    surround('\tretval = count_strings_kernel(argv);', (20, 'COUNT ARGV ENTER'), (21, 'COUNT ARGV RETURN')),
    surround('\tretval = count_strings_kernel(envp);', (22, 'COUNT ENVP ENTER'), (23, 'COUNT ENVP RETURN')),
    surround('\tretval = bprm_stack_limits(bprm);', (24, 'STACK LIMITS ENTER'), (25, 'STACK LIMITS RETURN')),
    surround('\tretval = copy_string_kernel(bprm->filename, bprm);', (26, 'COPY FILENAME ENTER'), (27, 'COPY FILENAME RETURN')),
    surround('\tretval = copy_strings_kernel(bprm->envc, envp, bprm);', (28, 'COPY ENVP ENTER'), (29, 'COPY ENVP RETURN')),
    surround('\tretval = copy_strings_kernel(bprm->argc, argv, bprm);', (30, 'COPY ARGV ENTER'), (31, 'COPY ARGV RETURN')),
])
section('static struct linux_binprm *alloc_bprm(', '\nDEFINE_CLASS(bprm,', [
    surround('\tfile = do_open_execat(fd, filename, flags);', (5, 'OPEN EXEC ENTER'), (6, 'OPEN EXEC RETURN')),
    surround('\tbprm = kzalloc_obj(*bprm);', (7, 'BINPRM KZALLOC ENTER'), (8, 'BINPRM KZALLOC RETURN')),
    surround('\tretval = bprm_mm_init(bprm);', (9, 'BINPRM MM ENTER'), (10, 'BINPRM MM RETURN')),
])
section('static int bprm_mm_init(', '\nstruct user_arg_ptr {', [
    surround('\tbprm->mm = mm = mm_alloc();', (11, 'MM ALLOC ENTER'), (12, 'MM ALLOC RETURN')),
    ('\ttask_lock(current->group_leader);', mark(13, 'TASK LOCK ENTER') + '\ttask_lock(current->group_leader);'),
    ('\ttask_unlock(current->group_leader);', '\ttask_unlock(current->group_leader);\n' + mark(14, 'TASK LOCK RETURN')),
    surround('\terr = create_init_stack_vma(bprm->mm, &bprm->vma, &bprm->p);', (15, 'STACK VMA ENTER'), (16, 'STACK VMA RETURN')),
])
section('static struct file *do_open_execat(', '\nstruct file *open_exec(', [
    surround('\tfile = do_file_open(fd, name, &open_exec_flags);', (17, 'FILE OPEN ENTER'), (18, 'FILE OPEN RETURN')),
    surround('\terr = exe_file_deny_write_access(file);', (19, 'DENY WRITE ENTER'), (40, 'DENY WRITE RETURN')),
])
section('int copy_string_kernel(', '\nEXPORT_SYMBOL(copy_string_kernel);', [
    surround('\t\tpage = get_arg_page(bprm, pos, 1);', (32, 'ARG PAGE ENTER'), (33, 'ARG PAGE RETURN')),
    surround('\t\tflush_arg_page(bprm, pos & PAGE_MASK, page);', (34, 'ARG FLUSH ENTER'), (35, 'ARG FLUSH RETURN')),
    surround('\t\tmemcpy_to_page(page, offset_in_page(pos), arg, bytes_to_copy);', (36, 'ARG MEMCPY ENTER'), (37, 'ARG MEMCPY RETURN')),
])
section('static int copy_strings_kernel(', '\nint setup_arg_pages(', [
    surround('\t\tcond_resched();', (38, 'RESCHED ENTER'), (39, 'RESCHED RETURN')),
])
prefix = '''extern void a6_diag_timer_row(unsigned int row, const char *text);
static int a6_exec_prep_active;
static void a6_exec_prep_mark(const char *text)
{
    if (a6_exec_prep_active) a6_diag_timer_row(3, text);
}
'''
p.write_text(prefix + s)

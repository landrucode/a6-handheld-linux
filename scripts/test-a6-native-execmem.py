#!/usr/bin/env python3
"""Run actual ARM allocator setup against the observed N42 framebuffer range."""
from pathlib import Path
import importlib.util,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('patch',ROOT/'scripts/patch-a6-native-execmem.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=subprocess.check_output(['git','-C',str(ROOT/'.deps/linux'),'show','HEAD:arch/arm/mm/init.c'],text=True)
modified=m.render(original)
def setup(s):
 a=s.index('struct execmem_info __init *execmem_arch_setup(void)');b=s.index('\n#endif /* CONFIG_MMU */',a);return s[a:b]
h='''#include <assert.h>
#include <stdbool.h>
#define __init
#define CONFIG_ARM_MODULE_PLTS 1
#define IS_ENABLED(x) (x)
#define BUILD_BUG_ON(x) _Static_assert(!(x),"PLTs required")
#define EXECMEM_DEFAULT 0
#define MODULES_VADDR 0xbf800000UL
#define MODULES_END 0xc0000000UL
#define VMALLOC_START 0xf0800000UL
#define VMALLOC_END 0xff800000UL
#define PAGE_KERNEL_EXEC 0x1234UL
struct range{unsigned long start,end,pgprot,alignment,fallback_start,fallback_end;};
struct execmem_info{struct range ranges[1];};
static struct execmem_info execmem_info;
'''
old=setup(original).replace('execmem_arch_setup','old_setup')
new=setup(modified)
main='''int main(void){
struct range before=old_setup()->ranges[0],after=execmem_arch_setup()->ranges[0];
assert(before.start<=0xbf80d100UL && before.end>0xbf80d100UL);
assert(after.start>=0xc0000000UL && after.end>after.start);
assert(after.pgprot==before.pgprot && after.alignment==before.alignment);
assert(after.fallback_start==VMALLOC_START && after.fallback_end==VMALLOC_END);
return 0;}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(h+old+new+main)
 subprocess.run(['cc','-std=c11',str(p/'t.c'),'-o',str(p/'t')],check=True)
 subprocess.run([str(p/'t')],check=True)
print('PASS actual ARM execmem setup: observed address collides in original, new range excludes framebuffer, permissions/alignment preserved, PLTs required')

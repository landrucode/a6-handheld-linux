#!/usr/bin/env python3
"""Keep N42 native modules out of the inherited framebuffer identity window."""
from pathlib import Path
import sys

def render(source):
 old='''\t\t\t\t.start\t= MODULES_VADDR,
\t\t\t\t.end\t= MODULES_END,'''
 new='''\t\t\t\t/* N42: bf600000..bfffffff retains the iBEC
\t\t\t\t * framebuffer identity mappings. Use the standard
\t\t\t\t * ARM PLT-capable vmalloc area for executable memory.
\t\t\t\t * Normal module RO/X permissions remain unchanged.
\t\t\t\t */
\t\t\t\t.start\t= VMALLOC_START,
\t\t\t\t.end\t= VMALLOC_END,'''
 if source.count(old)!=1:raise ValueError('pinned ARM execmem range changed')
 source=source.replace(old,new)
 old='''struct execmem_info __init *execmem_arch_setup(void)
{
'''
 new=old+'\tBUILD_BUG_ON(!IS_ENABLED(CONFIG_ARM_MODULE_PLTS));\n'
 if source.count(old)!=1:raise ValueError('pinned ARM execmem setup changed')
 return source.replace(old,new)
if __name__=='__main__':
 p=Path(sys.argv[1])/'arch/arm/mm/init.c';p.write_text(render(p.read_text()))

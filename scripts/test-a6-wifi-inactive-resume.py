#!/usr/bin/env python3
"""Execute the actual scoped inactive-resume filter over its state matrix."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
 root=Path(td);host=root/'drivers/usb/host';host.mkdir(parents=True)
 for name in ('ehci.h','ehci-hub.c','ehci-hcd.c'):
  (host/name).write_bytes(subprocess.check_output(['git','-C',str(ROOT/'.deps/linux'),'show','HEAD:drivers/usb/host/'+name]))
 subprocess.run(['python3',str(ROOT/'scripts/patch-a6-ehci-trial.py'),str(root)],check=True)
 s=(host/'ehci-hub.c').read_text();a=s.index('\t\t/* A6 inactive resume indication:');b=s.index('\n\n\t\t// wPortChange',a);block=s[a:b]
 harness=r'''
#include <assert.h>
#include <stdbool.h>
#define PORT_RESUME 64U
#define PORT_SUSPEND 128U
struct ehci_hcd {bool a6_wlan_only,a6_forcing_resume;unsigned long suspended_ports,resuming_ports;unsigned a6_inactive_resumes;};
static bool test_bit(unsigned n,unsigned long *p){return !!(*p&(1UL<<n));}
static unsigned filter(struct ehci_hcd *ehci,unsigned wIndex,unsigned temp){
BLOCK
return temp;
}
int main(void){
 for(int trial=0;trial<2;trial++)for(unsigned port=0;port<4;port++)
 for(int resume=0;resume<2;resume++)for(int suspend=0;suspend<2;suspend++)
 for(int suspended=0;suspended<2;suspended++)for(int resuming=0;resuming<2;resuming++)for(int forcing=0;forcing<2;forcing++){
  struct ehci_hcd e={trial,forcing,suspended?(1UL<<port):0,resuming?(1UL<<port):0,0};
  unsigned raw=0x1005|(resume?PORT_RESUME:0)|(suspend?PORT_SUSPEND:0);
  bool inactive=trial&&port==3&&resume&&!suspend&&!suspended&&!resuming&&!forcing;
  unsigned out=filter(&e,port,raw);
  assert(out==(inactive?(raw&~PORT_RESUME):raw));assert(e.a6_inactive_resumes==(unsigned)inactive);
  assert(e.suspended_ports==(suspended?(1UL<<port):0)&&e.resuming_ports==(resuming?(1UL<<port):0));
 }
 return 0;
}
'''.replace('BLOCK',block)
 (root/'test.c').write_text(harness)
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(root/'test.c'),'-o',str(root/'test')],check=True)
 subprocess.run([str(root/'test')],check=True)
 assert s.count('/* A6 inactive resume indication: software view only. */') == 2
 assert 'ehci_readl(ehci, status_reg), retval' in s # diagnostic still reads physical bits
print('PASS actual inactive resume filter: 256 state combinations; genuine suspend/resume, forced pulse, other ports/controllers preserved; raw trace retained')

#!/usr/bin/env python3
"""Reproduce forced-resume polling interleaving using actual patched C."""
from pathlib import Path
import subprocess,tempfile,re
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as td:
 root=Path(td);host=root/'drivers/usb/host';host.mkdir(parents=True)
 for name in ('ehci.h','ehci-hub.c','ehci-hcd.c'):
  data=subprocess.check_output(['git','-C',str(ROOT/'.deps/linux'),'show','HEAD:drivers/usb/host/'+name])
  (host/name).write_bytes(data)
 subprocess.run(['python3',str(ROOT/'scripts/patch-a6-ehci-trial.py'),str(root)],check=True)
 s=(host/'ehci-hub.c').read_text()
 guard=re.search(r'if \(\(temp & PORT_RESUME\).*?\) \{',s,re.S).group().removesuffix(' {')
 a=s.index('\t\t\tif (ehci->a6_wlan_only && wIndex == 3) {',s.index('case USB_PORT_FEAT_RESET:'))
 b=s.index('\n\t\t\tif (temp & (PORT_SUSPEND|PORT_RESUME))',a)
 block=s[a:b]
 harness=r'''
#include <stdbool.h>
#include <stdint.h>
#include <assert.h>
#define PORT_RESUME 0x40U
#define PORT_RWC_BITS 0x2aU
struct ehci_hcd {bool a6_wlan_only,a6_forcing_resume,resuming;int lock;unsigned long resuming_ports,suspended_ports,reset_done[4];};
struct usb_hcd {struct {unsigned long resuming_ports;unsigned refs;} self;};
static struct usb_hcd core;
static unsigned raw, calls, writes, ends;
static bool test_and_clear_bit(unsigned n,unsigned long *p){bool old=!!(*p&(1UL<<n));*p&=~(1UL<<n);return old;}
static void clear_bit(unsigned n,unsigned long *p){*p&=~(1UL<<n);}
static int current_lock(void);
static void usb_hcd_end_port_resume(void *bus,unsigned n){assert(bus==&core.self&&current_lock());ends++;if(core.self.resuming_ports&(1UL<<n)){core.self.resuming_ports&=~(1UL<<n);assert(core.self.refs);core.self.refs--;}}

static struct ehci_hcd *current;
static unsigned int current_index;
static int current_lock(void){return current->lock;}
static bool legacy;
static void poll(struct ehci_hcd *ehci,unsigned int wIndex,unsigned temp){
 if(legacy) {if(temp & PORT_RESUME)ehci->resuming=true;}
 else GUARD ehci->resuming=true;
}
static void ehci_writel(struct ehci_hcd *e,unsigned v,unsigned *reg){assert(e->lock);raw=v;writes++;}
static unsigned ehci_readl(struct ehci_hcd *e,unsigned *reg){assert(e->lock);return raw;}
#define spin_unlock_irqrestore(lockptr,flags) ((void)(flags),current->lock=0)
#define spin_lock_irqsave(lockptr,flags) ((void)(flags),current->lock=1)
static void msleep(unsigned n){assert(n==20&&!current->lock&&current->a6_forcing_resume);calls++;poll(current,current_index,raw);}
static void force(struct ehci_hcd *ehci,unsigned int wIndex){struct usb_hcd *hcd=&core;unsigned temp=raw,flags=0;unsigned *status_reg=&raw;current=ehci;current_index=wIndex;
BLOCK
}
int main(void){
 for(int old=0;old<2;old++){
  struct ehci_hcd e={.a6_wlan_only=true,.lock=1};raw=0x1005;legacy=old;calls=writes=0;
  force(&e,3);assert(calls==1&&writes==2&&e.lock&&!e.a6_forcing_resume&&raw==0x1005);
  assert(e.resuming==!!old); /* Old helper leaves stale resume state. */
 }
 legacy=false;
 for(int pending=0;pending<2;pending++){
  struct ehci_hcd e={.a6_wlan_only=true,.lock=1,.resuming_ports=1UL<<1,.suspended_ports=1UL<<1};
  core.self.resuming_ports=1UL<<1;core.self.refs=1;ends=0;raw=0x1005;
  if(pending){e.resuming_ports|=1UL<<3;e.suspended_ports|=1UL<<3;e.reset_done[3]=123;core.self.resuming_ports|=1UL<<3;core.self.refs++;}
  force(&e,3);
  assert(e.resuming_ports==(1UL<<1)&&e.suspended_ports==(1UL<<1)&&e.reset_done[3]==0);
  assert(core.self.resuming_ports==(1UL<<1)&&core.self.refs==1&&ends==(unsigned)pending);
  force(&e,3);assert(ends==(unsigned)pending&&core.self.refs==1);
 }
 for(int trial=0;trial<2;trial++)for(unsigned port=0;port<4;port++)for(int forcing=0;forcing<2;forcing++){
  struct ehci_hcd e={.a6_wlan_only=trial,.a6_forcing_resume=forcing,.lock=1};
  poll(&e,port,PORT_RESUME);assert(e.resuming==!(trial&&port==3&&forcing));
  e.resuming=false;poll(&e,port,0);assert(!e.resuming);
 }
 for(unsigned port=0;port<3;port++){
  struct ehci_hcd e={.a6_wlan_only=true,.lock=1};calls=writes=0;force(&e,port);assert(!calls&&!writes);
 }
 struct ehci_hcd e={.lock=1};calls=writes=0;force(&e,3);assert(!calls&&!writes);
 return 0;
}
'''.replace('GUARD',guard).replace('BLOCK',block)
 (root/'test.c').write_text(harness)
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(root/'test.c'),'-o',str(root/'test')],check=True)
 subprocess.run([str(root/'test')],check=True)
 assert 'ehci->a6_port_traces < 24' in s
print('PASS actual patched forced-resume interleaving: old helper leaves remote-wake state; scoped guard prevents it; pending reset clears resume/deadline and balances core reference once; other ports/general/real wake paths preserved')

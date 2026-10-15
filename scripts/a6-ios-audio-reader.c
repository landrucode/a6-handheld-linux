/* N42 iOS 10.3.4 stock capture, using Socket's RAM-access implementation.
 * Build against Socket exploit headers/objects and a private iOS SDK.
 * Peripheral access is read-only and uses existing kernel VA mappings.
 * Kernel access borrows/restores the reader's seatbelt slot and retains
 * one port/task reference to protect the imported kernel-task right.
 * Socket's global remap_kernel_task / run_oob_entry(true) is NOT called.
 * Never reads MCA TX/RX FIFO data ports. Off audio gates are not enabled.
 * Commands: p playing, r recording, d playback+recording, m IIS0 page series, i idle-after, q exits.
 */
#include <sys/time.h>
#include "memory.h"
#include "oob_entry.h"
#include "util.h"
void status(const char *s) { (void)s; }
static unsigned lookup(unsigned pa) {
  unsigned l1[4096];
  physread_buf(kinfo->kern_tte_phys, l1, sizeof(l1));
  for (unsigned i = 2048; i < 4096; i++) {
    unsigned d = l1[i];
    if ((d & 3) == 2 && (d & 0xfff00000) == (pa & 0xfff00000))
      return (i << 20) | (pa & 0xfffff);
    if ((d & 3) == 1) {
      unsigned l2[256];
      physread_buf(d & 0xfffffc00, l2, sizeof(l2));
      for (unsigned j = 0; j < 256; j++) {
        unsigned t = l2[j];
        if ((t & 3) >= 2 && (t & 0xfffff000) == (pa & 0xfffff000))
          return (i << 20) | (j << 12) | (pa & 4095);
        if ((t & 3) == 1 && (t & 0xffff0000) == (pa & 0xffff0000))
          return (i << 20) | (j << 12) | (pa & 4095);
      }
    }
  }
  return 0;
}
static unsigned read_errors;
static int readreg(mach_port_t port, unsigned pa) {
  unsigned va = lookup(pa), v = 0;
  mach_vm_size_t n = 0;
  int rc =
      va ? mach_vm_read_overwrite(port, va, 4, (mach_vm_address_t)&v, &n) : 4;
  printf("register pa=%08x va=%08x rc=%d n=%llu value=%08x\n", pa, va, rc, n,
         v);
  if (rc || n != 4)
    read_errors++;
  return rc || n != 4;
}
extern CFTypeRef IORegistryEntryCreateCFProperty(mach_port_t, CFStringRef,
                                                 CFAllocatorRef, uint32_t);
extern int IOObjectRelease(mach_port_t);
static void property(const char *name) {
  mach_port_t o = IOServiceGetMatchingService(0, IOServiceMatching(name));
  printf("PROPERTY %s CodecRegisterData\n", name);
  if (!o) {
    puts("service_missing");
    return;
  }
  CFStringRef k = CFSTR("CodecRegisterData");
  CFTypeRef v = IORegistryEntryCreateCFProperty(o, k, NULL, 0);
  IOObjectRelease(o);
  if (!v) {
    puts("unavailable");
    return;
  }
  CFDataRef d = CFPropertyListCreateXMLData(NULL, v);
  CFRelease(v);
  if (d) {
    printf("%.*s\n", (int)CFDataGetLength(d), CFDataGetBytePtr(d));
    CFRelease(d);
  } else
    puts("serialization_failed");
}
static unsigned value(mach_port_t port, unsigned pa) {
  unsigned va = lookup(pa), v = 0;
  mach_vm_size_t n = 0;
  int rc =
      va ? mach_vm_read_overwrite(port, va, 4, (mach_vm_address_t)&v, &n) : 4;
  if (rc || n != 4)
    return ~0U;
  return v;
}
/* IIS0 page snapshots never consume the RX data port (+0x38). */
static int iis0_page(mach_port_t port, unsigned index) {
  unsigned parent=value(port,0x3f1010a0), gate=value(port,0x3f1010a4);
  struct timeval tv; gettimeofday(&tv,NULL);
  printf("IIS0_PAGE index=%u time_us=%llu parent=%08x gate=%08x\n",index,
         (unsigned long long)tv.tv_sec*1000000+tv.tv_usec,parent,gate);
  if(parent==~0U || gate==~0U || (parent&255)!=255 || (gate&255)!=255) {
    puts("iis0_page_skipped_gate_not_active");return 1;
  }
  unsigned va=lookup(0x34190000);
  if(!va){puts("iis0_page_mapping_missing");return 1;}
  for(unsigned off=0;off<0x100;off+=4) {
    if(off==0x38 || off==0xb8){printf("iis0_data_%03x_skipped\n",off);continue;}
    unsigned v=0;mach_vm_size_t n=0;
    int rc=mach_vm_read_overwrite(port,va+off,4,(mach_vm_address_t)&v,&n);
    printf("iis0_register index=%u offset=%02x rc=%d n=%llu value=%08x\n",index,off,rc,n,v);
    if(rc || n!=4)read_errors++;
  }
  printf("IIS0_PAGE_END index=%u errors=%u\n",index,read_errors);
  return read_errors ? 1 : 0;
}
static int snapshot(mach_port_t port) {
  unsigned gate[] = {0xa0, 0xa4, 0xa8, 0xac, 0xb0, 0xe0, 0xf0};
  for (unsigned i = 0; i < 7; i++)
    readreg(port, 0x3f101000 + gate[i]);
  unsigned gpios[] = {9, 42, 90, 91};
  for (unsigned i = 0; i < 4; i++)
    readreg(port, 0x3fa00000 + 4 * gpios[i]);
  for (unsigned i = 0; i < 7; i++)
    for (unsigned j = 0; j < 3; j++)
      readreg(port, 0x3f1002b0 + 16 * i + 4 * j);
  unsigned parent = value(port, 0x3f1010a0), mca = value(port, 0x3f1010e0),
           i2s = value(port, 0x3f1010ac);
  if (parent != ~0U && (parent & 255) == 255) {
    unsigned routes[] = {0,4,8,12,16,20,24,28,32,36,40,44,48,52,56,60,64,68,72,76,80};
    for (unsigned i = 0; i < sizeof(routes)/sizeof(routes[0]); i++)
      readreg(port, 0x3fa01000 + routes[i]);
  } else
    puts("switch_skipped_parent_gate_not_active");
  for (unsigned bus=0; bus<2; bus++) {
    unsigned g=bus ? value(port,0x3f1010b0) : mca;
    if(parent!=~0U && g!=~0U && (parent&255)==255 && (g&255)==255) {
      unsigned offs[]={0,4,8,12,16,20,24,28,32,36,44,48,52,56,64};
      for(unsigned i=0;i<sizeof(offs)/sizeof(offs[0]);i++)
        readreg(port,0x34196000+0x1000*bus+offs[i]);
    } else printf("mca%u_skipped_gate_not_active\n",bus);
  }
  if (parent != ~0U && i2s != ~0U && (parent & 255) == 255 &&
      (i2s & 255) == 255) {
    unsigned offs[] = {0, 8, 0x34};
    for (unsigned i = 0; i < 3; i++)
      readreg(port, 0x34192000 + offs[i]);
  } else
    puts("i2s2_skipped_gate_not_active");
  if (parent != ~0U && (parent & 255) == 255) {
    for (unsigned bus = 0; bus < 2; bus++) {
      unsigned g = value(port, 0x3f1010a4 + 4 * bus);
      if (g != ~0U && (g & 255) == 255) {
        unsigned offs[] = {0,4,8,12,16,20,24,28,32,36,40,44,48,52,60,64};
        for (unsigned i = 0; i < sizeof(offs)/sizeof(offs[0]); i++)
          readreg(port, 0x34190000 + 0x1000 * bus + offs[i]);
      }
    }
  }
  property("AppleCS35L19Amp");
  property("AppleCS42L65Audio");
  printf("snapshot_read_errors=%u\n", read_errors);
  return read_errors ? 1 : 0;
}
int main(void) {
  setbuf(stdout, NULL);
  int rc = run_oob_entry(false);
  printf("readonly_init=%d\n", rc);
  if (rc)
    return 1;
  unsigned slot = kinfo->self_task_addr + kinfo->offsets.task.itk_seatbelt;
  unsigned saved = kread32(slot);
  printf("task_identity pid=%u found_pid=%u self_port=%08x self_kobject=%08x slot=%08x saved=%08x\n",getpid(),kread32(kinfo->self_proc_addr+8),kread32(kinfo->self_task_addr+0x9c),kread32(kread32(kinfo->self_task_addr+0x9c)+0x50),slot,saved);
  unsigned bits = kread32(kinfo->kern_port_addr);
  printf("kernel_port_bits=%08x\n", bits);
  if ((bits & 0x800003ffU) != 0x80000002U) {
    puts("kernel_port_type_mismatch");
    return 1;
  }
  unsigned pref = kread32(kinfo->kern_port_addr + 4),
           tref = kread32(kinfo->kern_task_addr + 8);
  printf("kernel_refs_before port=%u task=%u\n", pref, tref);
  if (!pref || !tref || pref > 0x100000 || tref > 0x100000)
    return 1;
  kwrite32(kinfo->kern_port_addr + 4, pref + 1);
  kwrite32(kinfo->kern_task_addr + 8, tref + 1);
  mach_port_t port = 0;
  kwrite32(slot, kinfo->kern_port_addr);
  for(unsigned attempt=0;attempt<100;attempt++) {
    kwrite32(slot, kinfo->kern_port_addr);
    if(!attempt)printf("slot_write_readback=%08x\n",kread32(slot));
    usleep(1000);
    rc = task_get_special_port(mach_task_self(), TASK_SEATBELT_PORT, &port);
    if(rc || MACH_PORT_VALID(port))break;
  }
  kwrite32(slot, saved);
  unsigned restored = kread32(slot);
  printf("direct_kernel_port rc=%d port=%u slot_restore=%d\n", rc, port,
         restored == saved);
  if (rc || !port || restored != saved)
    return 1;
  printf("kernel_refs_acquired port=%u task=%u\n",
         kread32(kinfo->kern_port_addr + 4),
         kread32(kinfo->kern_task_addr + 8));
  puts("SNAPSHOT idle-before");
  rc = snapshot(port);
  puts("READY playback-or-idle-command");
  int ch;
  while ((ch = getchar()) != EOF) {
    if (ch == 'q')
      break;
    if (ch != 'p' && ch != 'i' && ch != 'r' && ch != 'd' && ch != 'm')
      continue;
    read_errors = 0;
    if(ch=='m') {
      puts("SNAPSHOT recording-iis0-page-series");
      for(unsigned i=0;i<16;i++){rc|=iis0_page(port,i);usleep(20000);}
      puts("READY playback-or-idle-command");continue;
    }
    printf("SNAPSHOT %s\n", ch == 'p' ? "playing" : ch == 'r' ? "recording" : ch == 'd' ? "playback-recording" : "idle-after");
    rc |= snapshot(port);
    puts("READY playback-or-idle-command");
  }
  mach_port_deallocate(mach_task_self(), port);
  printf("kernel_refs_released port=%u task=%u bits=%08x\n",
         kread32(kinfo->kern_port_addr + 4), kread32(kinfo->kern_task_addr + 8),
         kread32(kinfo->kern_port_addr));
  return rc;
}

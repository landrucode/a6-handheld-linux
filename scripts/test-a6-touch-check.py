#!/usr/bin/env python3
"""Exercise the actual CHECK handler against fault-injecting fake MMIO."""
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
source = (repo / 'kernel/platform/a6-touch-check.inc').read_text()
source = '\n'.join(x for x in source.splitlines() if not x.startswith('#include'))
preamble = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <sys/types.h>
typedef uint32_t u32;
typedef uint8_t u8;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define U32_MAX UINT32_MAX
#define CAP_SYS_RAWIO 1
#define __init
#define late_initcall(x)
#define pr_info(...) ((void)0)
#define A6_TOUCH_GATE 0xe8
#define A6_TOUCH_CS 0xc4
#define A6_TOUCH_RESET 0x39c
#define A6_TOUCH_ATN 0x324
struct kobject { int unused; };
struct attribute { int unused; };
struct kobj_attribute { struct attribute attr; };
struct attribute_group { const char *name; struct attribute **attrs; };
#define __ATTR(...) { {0} }
static struct kobject *firmware_kobj;
static int sysfs_create_group(void *a, const void *b) { return 0; }
static int of_machine_is_compatible(const char *s) { return 1; }
#define sysfs_emit(...) 0
#define sysfs_emit_at(...) 0
static int a6_touch_lock;
#define mutex_lock(x) ((void)0)
#define mutex_unlock(x) ((void)0)
static bool privileged = true;
static int capable(int x) { return privileged; }
static int sysfs_streq(const char *a, const char *b) { return !strcmp(a,b); }
static unsigned char pmgr[4096], gpio[4096], spi[4096];
static void *a6_touch_pmgr=pmgr, *a6_touch_gpio=gpio, *a6_touch_spi=spi;
static unsigned writes, fifo_reads, polls, delays, received;
static bool running;
static unsigned queued;
static int fault;
static void msleep(unsigned n) { delays += n * 1000; }
static void udelay(unsigned n) { delays += n; }
static u32 readl(void *p) {
 if (p == spi+8 && running) {
  polls++;
  if (fault==2) return 0;
  if (fault==3) return U32_MAX;
  if (fault==4) return 17 << 11;
  return (queued-received) << 11;
 }
 if (p == spi+0x20) {
  fifo_reads++; received++;
  return received==1 ? (fault==1 ? 0xff : 0xd0) : 0;
 }
 return *(u32*)p;
}
static void writel(u32 v, void *p) {
 writes++;
 if (fault==5 && p==spi+4 && v==8) return; /* Failed restoration. */
 if (p == spi+0x10) {
  if (running) queued++; /* Model FIFO writes accepted only while RUN. */
  return;
 }
 if (p == spi) {
  running = v & 1;
  if (v & 12) { received=0; queued=0; }
 }
 if (p==spi+8) *(u32*)p=0; else *(u32*)p=v;
}
'''
tests = r'''
static void setup(int f) {
 memset(pmgr,0,sizeof(pmgr)); memset(gpio,0,sizeof(gpio)); memset(spi,0,sizeof(spi));
 *(u32*)(pmgr+A6_TOUCH_GATE)=0x2ff;
 *(u32*)(gpio+A6_TOUCH_CS)=0x202;
 *(u32*)(gpio+A6_TOUCH_RESET)=0x202;
 *(u32*)(spi+4)=8; *(u32*)(spi+12)=3; *(u32*)(spi+48)=1;
 privileged=true; running=false; fault=f;
 writes=fifo_reads=polls=delays=received=queued=0;
 a6_check_attempted=false; a6_check_restored=false; a6_check_received=0;
 memset(a6_check_rx,0,4);
}
int main(void) {
 unsigned char original_spi[4096], original_gpio[4096];
 int expected[]={16,-EPROTO,-ETIMEDOUT,-EIO,-EIO,-EUCLEAN};
 for (int f=0; f<6; f++) {
  setup(f); memcpy(original_spi,spi,4096); memcpy(original_gpio,gpio,4096);
  assert(a6_check_run_store(NULL,NULL,"check-bootloader",16)==expected[f]);
  assert(a6_check_attempted && fifo_reads<=4 && polls<=10002);
  assert(a6_check_restored == (f!=5));
  assert(delays<=120010 && !running);
  assert((memcmp(original_spi,spi,4096)!=0) == (f==5));
  assert(!memcmp(original_gpio,gpio,4096));
  unsigned before=writes;
  assert(a6_check_run_store(NULL,NULL,"check-bootloader",16)==-EALREADY);
  assert(writes==before);
 }
 setup(0); privileged=false;
 assert(a6_check_run_store(NULL,NULL,"check-bootloader",16)==-EPERM && !writes);
 setup(0);
 assert(a6_check_run_store(NULL,NULL,"other",5)==-EINVAL && !writes);
 for (int condition=0; condition<4; condition++) {
  setup(0);
  if(condition==0) *(u32*)(pmgr+A6_TOUCH_GATE)=0x200;
  if(condition==1) *(u32*)(gpio+A6_TOUCH_CS)=0x203;
  if(condition==2) *(u32*)(spi)=1;
  if(condition==3) *(u32*)(spi+8)=0x800;
  assert(a6_check_run_store(NULL,NULL,"check-bootloader",16)==-EBUSY && !writes);
  assert(!a6_check_attempted);
 }
 puts("PASS actual CHECK handler: reply, mismatch, timeout, invalid FIFO, cleanup, one-shot, privileges and idle guards");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-check-test-') as tmp:
    c = Path(tmp) / 'test.c'
    c.write_text(preamble + source + tests)
    exe = Path(tmp) / 'test'
    subprocess.run(['cc', '-std=gnu11', '-O2', '-fsanitize=undefined', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)

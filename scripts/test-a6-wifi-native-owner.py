#!/usr/bin/env python3
"""Execute actual native start/stop ownership logic with MMIO/PMU faults."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'kernel/platform/a6-wifi-ehci-enum.inc').read_text()
a=s.index('static ssize_t a6_wifi_enum_run');b=s.index('#ifdef A6_WIFI_NATIVE\nstatic ssize_t a6_wifi_native_show',a)
fn=s[a:b]
states=s[s.index('static DEFINE_MUTEX(a6_wifi_enum_lock);'):s.index('/* Serialize individual PMU')]
h=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <sys/types.h>
#define A6_WIFI_NATIVE 1
#define __iomem
#define DEFINE_MUTEX(n) int n
#define CAP_SYS_RAWIO 1
#define BIT(n) (1U<<(n))
#define pr_info(...) ((void)0)
typedef uint32_t u32;typedef uint8_t u8;
struct kobject{};struct kobj_attribute{};
static int locked, maps, unmaps, reset_writes, stop_order, writes, native_calls;
static bool live, startup_fail, cap=true;
static u32 pmgr[2048],control[1024],phy[1024],ehci[1024];
static void *a6_native_pmgr,*a6_native_control,*a6_native_phy,*a6_native_ehci;
static bool a6_auto_enabled=true,a6_auto_fault,a6_auto_paused,a6_low_enabled=true;
static bool a6_low_triggered,a6_low_attended_trial,a6_low_attended_plugged;
static u8 reset_value=9;
static int capable(int x){return cap;}
static bool sysfs_streq(const char*a,const char*b){return !strcmp(a,b);}
static void mutex_lock(int*x){assert(!locked);locked=1;}
static void mutex_unlock(int*x){assert(locked);locked=0;}
static void *ioremap(unsigned a,unsigned n){maps++;switch(a){case 0x3f100000:return pmgr;case 0x3f108000:return control;case 0x36000000:return phy;case 0x36400000:return ehci;default:assert(0);}return 0;}
static void iounmap(void*p){if(p)unmaps++;}
static u32 readl(void*p){return *(u32*)p;}
static void writel(u32 v,void*p){writes++;if(p==(void*)((char*)pmgr+0x108c))v=(v&~0xf0U)|((v&15)==15?0xf0:0);*(u32*)p=v;}
#define readl_poll_timeout(p,v,c,a,b) ((v)=readl(p),(c)?0:-ETIMEDOUT)
static void msleep(unsigned n){}
static int a6_wifi_reset_read(u8*p){*p=reset_value;return 0;}
static int a6_wifi_reset_write(u8 v,unsigned*n){(*n)++;reset_writes++;reset_value=v;return 0;}
static void a6_ehci_reset_trial(void){assert(!live);}
static int a6_ehci_trial(void*r,u32*w){w[0]=0x0a5c;w[1]=0xbd1a;return 0;}
static int a6_ehci_native_start(void*r,u32*w){native_calls++;if(startup_fail)return -EIO;live=true;w[0]=0x0a5c;w[1]=0xbd1a;return 0;}
static bool a6_ehci_native_active(void){return live;}
static void a6_ehci_native_stop(void){assert(live);live=false;stop_order=writes;}
'''
main=r'''
static ssize_t run(const char*c){ssize_t r=a6_wifi_enum_run(0,0,c,strlen(c));assert(!locked);return r;}
static void baseline(void){assert(!live&&!a6_native_pmgr&&reset_value==9&&pmgr[0x108c/4]==0x200&&phy[2]==0&&!(control[0]&4));assert(maps==unmaps);}
int main(void){pmgr[0x108c/4]=0x200;pmgr[0x1084/4]=pmgr[0x109c/4]=0x2ff;pmgr[0x2a4/4]=pmgr[0x2a8/4]=0x82000001;ehci[0]=0x01000010;ehci[0x14/4]=BIT(12);
 cap=false;assert(run("start-native-n42-wlan")==-EPERM);cap=true;
 a6_auto_fault=true;assert(run("start-native-n42-wlan")==-EPERM);a6_auto_fault=false;baseline();
 startup_fail=true;assert(run("start-native-n42-wlan")==-EIO);startup_fail=false;baseline();
 for(int i=0;i<3;i++){
  assert(run("start-native-n42-wlan")>0);assert(live&&a6_native_pmgr&&maps-unmaps==4&&a6_wifi_enum_restore==-EINPROGRESS);
  int prior=native_calls, prior_writes=writes;assert(run("start-native-n42-wlan")>0&&native_calls==prior&&writes==prior_writes);
  assert(run("enumerate-once-n42-wlan")==-EBUSY&&live);
  a6_auto_fault=true;assert(run("stop-native-n42-wlan")>0);a6_auto_fault=false;
  assert(stop_order==prior_writes&&writes>stop_order&&a6_wifi_enum_restore==0);baseline();
  prior_writes=writes;assert(run("stop-native-n42-wlan")>0&&writes==prior_writes);
 }
 assert(run("enumerate-once-n42-wlan")>0);baseline();
 puts("PASS actual native owner: start failure unwind, retained mappings, idempotent start/stop, trial exclusion, repeated stop/start, disconnect before restoration, stop despite guard fault");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(h+states+fn+main)
 subprocess.run(['cc','-std=gnu11','-fsanitize=address,undefined',str(p/'t.c'),'-o',str(p/'t')],check=True)
 subprocess.run([str(p/'t')],check=True)

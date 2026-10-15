#!/usr/bin/env python3
"""Exercise actual raw-run orchestration: one setup, both banks, final restore."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/platform/a6-audio-alsa.inc').read_text()
actual=s[s.index('struct a6_raw_result {'):s.index('static ssize_t a6_raw_status(')]
code=r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <sys/types.h>
typedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;
#define U32_MAX UINT32_MAX
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min(a,b) ((a)<(b)?(a):(b))
struct kobject;struct kobj_attribute;
struct a6_s_stream {void *sub;bool capture,ready;int cleanup;unsigned setup_stage,replay_mismatches;u32 failed_codec_reg,mismatch_regs[16];u8 mismatch_want[16],mismatch_got[16];u8 clear_before[2],clear_write[2],clear_after[2],clear_final[2];unsigned clear_attempts;bool clear_io_error;};
static struct a6_s_stream a6_s_streams[2];
static bool a6_s_raw_active;static unsigned a6_s_parent_users,setups,restores,reads[2];static int a6_s_mutex,a6_touch_lock,setup_error,cleanup_error;
static unsigned char iis[256];static void *a6_ac_iis=iis;static u64 now;
static void mutex_lock(int *m){assert(!*m);*m=1;}static void mutex_unlock(int *m){assert(*m);*m=0;}
static bool sysfs_streq(const char *a,const char *b){return !strcmp(a,b);}
static bool a6_s_guard(void){return true;}
static int a6_s_parent_get(struct a6_s_stream *s){a6_s_parent_users++;return 0;}
static int a6_s_capture_setup(struct a6_s_stream *s){assert(a6_touch_lock && a6_s_raw_active);setups++;s->setup_stage=7;s->ready=true;return setup_error;}
static int a6_s_restore(struct a6_s_stream *s){assert(a6_touch_lock && !s->ready);restores++;a6_s_parent_users=0;s->cleanup=cleanup_error;return cleanup_error;}
static u64 ktime_get_ns(void){return now;}static void udelay(unsigned us){now+=us*1000;}static void cond_resched(void){}
static u32 readl(void *p){unsigned off=(unsigned char *)p-iis,bank=off/128;assert(bank<2 && !a6_touch_lock);
 if(off%128==0x3c)return (reads[bank]<8 ? 8-reads[bank] : 0)<<13;
 assert(off%128==0x38 && reads[bank]<8);reads[bank]++;return bank ? 0x1234 : 0xabcd;}
'''+actual+r'''
int main(void){
 cleanup_error=-EUCLEAN;
 assert(a6_raw_run(0,0,"recording-banks-raw-restore",27)==-EUCLEAN);
 assert(setups==1 && restores==1 && reads[0]==8 && reads[1]==8);
 assert(a6_raw_results[0].elapsed>=250000000 && a6_raw_results[1].elapsed>=250000000);
 assert(a6_raw_results[0].cleanup==-EUCLEAN && a6_raw_results[1].cleanup==-EUCLEAN);
 assert(!a6_s_raw_active && !a6_s_parent_users);
 a6_s_streams[1].cleanup=0;setups=restores=reads[0]=reads[1]=0;setup_error=-EIO;cleanup_error=0;
 assert(a6_raw_run(0,0,"recording-banks-raw-restore",27)==-EIO);
 assert(setups==1 && restores==1 && !reads[0] && !reads[1]);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'raw.c';p.write_text(code);exe=Path(d)/'raw'
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: one setup, both banks before final restore, restore failures retained, setup failure unwound')

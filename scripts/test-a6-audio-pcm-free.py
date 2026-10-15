#!/usr/bin/env python3
"""Execute actual HW_FREE/close/restore: timers stop, ownership releases, failure latches."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/platform/a6-audio-alsa.inc').read_text()
assert '.hw_free=a6_s_hw_free' in s
restore=s[s.index('static int a6_s_restore(struct'):s.index('static int a6_s_play_setup(')]
free=s[s.index('static int a6_s_hw_free('):s.index('static int a6_s_prepare(')]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
typedef uint32_t u32;
#define U32_MAX UINT32_MAX
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v,x) ((v)=(x))
#define pr_err(...) ((void)0)
struct saved {void *p;u32 v;};
struct a6_s_stream {bool capture,ready,running,stopping,parent_owned;unsigned saved_count,gate_count,codec_dirty;int cleanup,timer,watchdog,fault_work;void *sub;struct saved saved[2];u32 gates[2],gate_before[2];};
struct runtime {void *private_data;};struct snd_pcm_substream {struct runtime *runtime;};
static unsigned char gpio[512],mca[256],iis[256],pmgr[512];
static void *a6_touch_gpio=gpio,*a6_af_mca=mca,*a6_ac_iis=iis,*a6_touch_pmgr=pmgr;
static bool a6_at_alive_active;static unsigned a6_s_parent_users=1;static u32 a6_s_parent_before=0x200;
static int a6_s_mutex,a6_touch_lock,codec_failure,cancelled,codec_calls,sleeps,writes;
static u32 readl(void *p){return *(u32 *)p;}static void writel(u32 v,void *p){*(u32 *)p=v;writes++;}
static int a6_af_poll(void *p,u32 m,u32 want){return 0;}
static int a6_s_restore_word(void *p,u32 v){writel(v,p);return 0;}
static int a6_s_codec_restore(struct a6_s_stream *s){codec_calls++;s->codec_dirty=0;return codec_failure;}
static void msleep(unsigned ms){assert(ms==21);sleeps++;}
static struct a6_s_stream *current;
static void hrtimer_cancel(int *p){assert(!current->ready);cancelled++;}
static void cancel_work_sync(int *p){cancelled++;}
static void mutex_lock(int *p){assert(!*p);*p=1;}static void mutex_unlock(int *p){assert(*p);*p=0;}
'''+restore+free+r'''
int main(void){
 struct a6_s_stream stream={.capture=true,.ready=true,.running=true,.codec_dirty=1,.parent_owned=true,.gate_count=1};current=&stream;
 struct runtime rt={&stream};struct snd_pcm_substream sub={&rt};stream.sub=&sub;stream.gates[0]=0xa4;stream.gate_before[0]=0x200;
 assert(!a6_s_hw_free(&sub));assert(!stream.ready && !stream.running && !stream.parent_owned && !a6_s_parent_users && cancelled==3 && codec_calls==1);
 assert(readl(pmgr+0xa4)==0x200 && readl(pmgr+0xa0)==0x200);
 assert(!a6_s_close(&sub) && !stream.sub && codec_calls==1);
 stream=(struct a6_s_stream){.capture=true,.ready=true,.running=true,.codec_dirty=1,.parent_owned=true,.sub=&sub};a6_s_parent_users=1;codec_failure=-EUCLEAN;
 assert(a6_s_hw_free(&sub)==-EUCLEAN && stream.cleanup==-EUCLEAN && !stream.running && !a6_s_parent_users);
 unsigned before=writes;assert(a6_s_close(&sub)==-EUCLEAN && stream.cleanup==-EUCLEAN && !stream.sub && writes==before);
 assert(a6_s_restore(&stream)==-EUCLEAN && writes==before);
 stream=(struct a6_s_stream){.ready=true,.running=true,.stopping=true};assert(!a6_s_hw_free(&sub) && sleeps==1 && !stream.running);
 assert(!a6_s_mutex && !a6_touch_lock);return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'test.c';p.write_text(code);exe=Path(d)/'test';subprocess.run(['cc','-fsanitize=address,undefined',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: actual HW_FREE stops service before release, restores ownership, close preserves errors, playback ramp retained')

#!/usr/bin/env python3
"""Execute actual PCM prepare: startup drains outside charger lock; unwind errors."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/platform/a6-audio-alsa.inc').read_text();a=s.index('static int a6_s_prepare(');b=s.index('static int a6_s_trigger(',a)
code=r'''
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
struct a6_s_stream {bool ready,capture,capture_half,running,stopping;int timer,watchdog,fault_work,cleanup,capture_left,pos,period,frames,consumed,last_tick,stop_frames,last_sample,error,setup_error;};
struct runtime {void *private_data;};struct snd_pcm_substream {struct runtime *runtime;};
static int a6_s_mutex,a6_touch_lock,hrtimer_resolution=1,restores,sleeps,fail;
#define WRITE_ONCE(v,x) ((v)=(x))
#define READ_ONCE(v) (v)
static void hrtimer_cancel(int *p){}static void cancel_work_sync(int *p){}
static void mutex_lock(int *p){assert(!*p);*p=1;}static void mutex_unlock(int *p){assert(*p);*p=0;}
static int a6_s_restore(struct a6_s_stream *s){restores++;return 0;}
static bool hrtimer_highres_enabled(void){return true;}static bool a6_s_guard(void){return fail!=2;}
static int a6_s_parent_get(struct a6_s_stream *s){return 0;}
static struct a6_s_stream *current;
static int a6_s_capture_setup(struct a6_s_stream *s){s->ready=true;return 0;}
static int a6_s_play_setup(struct a6_s_stream *s){s->ready=true;return 0;}
static void msleep(unsigned ms){assert(ms==150 && a6_s_mutex && !a6_touch_lock && current->ready && !current->running);sleeps++;if(fail==1){current->error=-EIO;current->ready=false;}}
'''+s[a:b]+r'''
int main(void){struct a6_s_stream stream={.capture=true};current=&stream;struct runtime rt={&stream};struct snd_pcm_substream sub={&rt};
 assert(!a6_s_prepare(&sub) && sleeps==1 && restores==1 && stream.ready);
 fail=1;assert(a6_s_prepare(&sub)==-EIO && sleeps==2 && restores==3 && !stream.ready);
 stream=(struct a6_s_stream){0};fail=0;assert(!a6_s_prepare(&sub) && sleeps==2 && restores==4);
 assert(!a6_touch_lock && !a6_s_mutex);return 0;}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'test.c';p.write_text(code);exe=Path(d)/'test';subprocess.run(['cc','-fsanitize=address,undefined',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: actual PCM prepare drains startup outside charger lock, unwinds faults, and leaves playback unchanged')

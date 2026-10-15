#!/usr/bin/env python3
"""Exercise final codec restoration with settling and transfer failure models."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/platform/a6-audio-alsa.inc').read_text()
s=s[s.index('static int a6_s_codec_clear_probe('):s.index('static int a6_s_restore(')]
code=r'''
#include <stdint.h>
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
typedef uint64_t u64;typedef uint8_t u8;typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define pr_err(...) ((void)0)
static u32 a6_mic_codec_regs[]={0x4a,0x4b,0x238};
struct a6_s_stream {unsigned codec_dirty;u8 codec_before[3];u8 clear_before[2],clear_write[2],clear_after[2],clear_final[2];unsigned clear_attempts;bool clear_io_error;};
static bool a6_s_raw_active;
static u64 now;static unsigned writes,reads,sleeps;static int fail_write=-1;static bool stuck,fail_read;
static u64 ktime_get_ns(void){return now;}
static void usleep_range(unsigned lo,unsigned hi){now+=lo*1000;sleeps++;}
static int a6_ac_transfer(u32 reg,u8 *rb,bool write,u8 value){assert(write);unsigned n=writes++;return (int)n==fail_write ? -EIO : 0;}
static int a6_ac_read_reg(u32 reg,u8 *rb){assert(writes==3);reads++;if(fail_read)return -EIO;rb[4]=(stuck || now<2000000) ? 0x80 : 0;return 0;}
'''+s+r'''
int main(void){struct a6_s_stream stream={.codec_dirty=3};
 assert(!a6_s_codec_restore(&stream));assert(writes==3 && sleeps==2 && reads>=6 && !stream.codec_dirty);
 now=0;writes=reads=sleeps=0;stuck=true;stream.codec_dirty=3;
 assert(a6_s_codec_restore(&stream)==-EUCLEAN && now<=50000000 && sleeps<=50 && !stream.codec_dirty);
 stuck=false;now=2000000;
 for(int i=0;i<3;i++){writes=reads=0;stream.codec_dirty=3;fail_write=i;assert(a6_s_codec_restore(&stream)==-EUCLEAN && writes==3);}
 fail_write=-1;fail_read=true;writes=0;stream.codec_dirty=3;assert(a6_s_codec_restore(&stream)==-EUCLEAN);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'restore.c';p.write_text(code);exe=Path(d)/'restore'
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: final restore follows all writes, waits for settling, bounds stuck status and retains SPI failures')

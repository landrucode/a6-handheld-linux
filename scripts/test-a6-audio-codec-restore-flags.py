#!/usr/bin/env python3
"""Execute grouped flag probes and full final verification with IRQ relatching."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/platform/a6-audio-alsa.inc').read_text()
s=s[s.index('static int a6_s_codec_clear_probe('):s.index('static int a6_s_restore(')]
code=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
typedef uint64_t u64;typedef uint32_t u32;typedef uint8_t u8;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define pr_err(...) ((void)0)
static u32 a6_mic_codec_regs[]={0x4a,0x4f,0x4b};
struct a6_s_stream {unsigned codec_dirty;u8 codec_before[3],clear_before[2],clear_write[2],clear_after[2],clear_final[2];unsigned clear_attempts;bool clear_io_error;};
static bool a6_s_raw_active=true,source=true,summary=true,final_control_bad;
static unsigned writes,reads;static u32 read_log[256];static int fail_write=-1;static u64 now;
static u64 ktime_get_ns(void){return now;}static void usleep_range(unsigned lo,unsigned hi){now+=lo*1000;}
static int a6_ac_transfer(u32 reg,u8 *rb,bool write,u8 value){assert(write);unsigned n=writes++;if((int)n==fail_write)return -EIO;
 if(reg==0x4f && (value&1))source=false;
 if(reg==0x4a && (value&0x80))summary=false;
 return 0;}
static int a6_ac_read_reg(u32 reg,u8 *rb){assert(reads<256);read_log[reads++]=reg;
 if(source)summary=true;
 rb[4]=reg==0x4a ? 7|(summary ? 0x80 : 0) : reg==0x4f ? source : final_control_bad && writes>=7 ? 0x81 : 0x80;
 return 0;}
static void reset(void){source=summary=true;final_control_bad=false;writes=reads=0;now=0;fail_write=-1;}
'''+s+r'''
int main(void){struct a6_s_stream stream={.codec_dirty=3,.codec_before={7,0,0x80}};
 assert(!a6_s_codec_restore(&stream));assert(writes==7 && stream.clear_attempts==3 && !stream.clear_io_error && !source && !summary);
 assert(stream.clear_after[0]==7 && stream.clear_final[0]==7 && stream.clear_after[1]==0 && stream.clear_final[1]==0);
 assert(read_log[reads-3]==0x4a && read_log[reads-2]==0x4f && read_log[reads-1]==0x4b);
 reset();stream=(struct a6_s_stream){.codec_dirty=3,.codec_before={7,0,0x80}};final_control_bad=true;
 assert(a6_s_codec_restore(&stream)==-EUCLEAN);
 reset();stream=(struct a6_s_stream){.codec_dirty=3,.codec_before={7,0,0x80}};fail_write=3;
 assert(a6_s_codec_restore(&stream)==-EUCLEAN && stream.clear_io_error);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'flags.c';p.write_text(code);exe=Path(d)/'flags';subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: grouped flag clearing survives relatching, complete final readback catches new mismatch, SPI errors persist')

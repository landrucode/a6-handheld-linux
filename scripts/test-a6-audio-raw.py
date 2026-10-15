#!/usr/bin/env python3
"""Exercise the actual headless FIFO burst against distinct receive banks."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'kernel/platform/a6-audio-alsa.inc').read_text()
start=s.index('struct a6_raw_result {');end=s.index('static ssize_t a6_raw_run',start)
source_replay=s[s.index('static bool a6_s_codec_observed('):s.index('static int a6_s_capture_setup(')]
code=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;typedef uint64_t u64;typedef uint8_t u8;
#define U32_MAX UINT32_MAX
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min(a,b) ((a)<(b)?(a):(b))
static u64 now;static u64 ktime_get_ns(void){return now;}
static unsigned char iis[256];static void *a6_ac_iis=iis;
static unsigned counts[2],reads[2];static bool bad;
static u32 readl(void *p){
 unsigned off=(unsigned char *)p-iis,bank=off/128;
 assert(bank<2);
 if(off%128==0x3c)return bad ? U32_MAX : (counts[bank]<<13)|4;
 assert(off%128==0x38 && counts[bank]);counts[bank]--;reads[bank]++;
 return bank ? 0xabcd1234 : 0;
}
'''+s[start:end]+r'''
struct a6_s_stream {unsigned codec_dirty,replay_mismatches;u32 failed_codec_reg,mismatch_regs[16];u8 mismatch_want[16],mismatch_got[16];};
static bool a6_s_raw_active;static int transfers,fail_transfer=-1;
static u32 a6_mic_codec_regs[]={8,16,15};static u8 a6_mic_codec_values[]={0x77,0x80,2};
static int a6_ac_transfer(u32 reg,u8 *reply,bool write,u8 value){return transfers++==fail_transfer ? -ETIMEDOUT : 0;}
static int a6_ac_read_reg(u32 reg,u8 *reply){reply[4]=reg==8 ? 0x66 : reg==16 ? 0x80 : 2;return 0;}
'''+source_replay+r'''
int main(void){
 assert(a6_s_codec_observed(0x4a,0x87,0x07));
 assert(a6_s_codec_observed(0x4b,0,0x80));
 assert(a6_s_codec_observed(0x75,0,0x60));
 assert(a6_s_codec_observed(0x544,0x44,0x54));
 assert(a6_s_codec_observed(0x544,0x44,0x45));
 assert(!a6_s_codec_observed(0x4a,0x87,0x17));
 assert(!a6_s_codec_observed(0x544,0x44,0x55));
 assert(!a6_s_codec_observed(8,0x77,0x66));
 struct a6_raw_result r={0};counts[0]=64;counts[1]=8;
 assert(!a6_raw_burst(&r,0));assert(r.words==32 && r.nonzero==0 && reads[1]==0);
 assert((r.before[0]>>13)==64 && (r.after[0]>>13)==32);
 assert(!a6_raw_burst(&r,0));assert(r.words==64 && r.samples==0 && r.startup_samples==16);
 assert(!a6_raw_burst(&r,0));assert(r.words==64);
 assert(!a6_raw_burst(&r,128));assert(r.words==72 && r.nonzero==8 && r.samples==8 && r.raw[0]==0xabcd1234);
 assert(reads[0]==64 && reads[1]==8);
 bad=true;assert(a6_raw_burst(&r,128)==-EIO && r.words==72);
 for(unsigned i=0;i<40;i++){bad=false;counts[1]=127;assert(!a6_raw_burst(&r,128));}
 assert(r.probes==8 && r.samples==64);
 struct a6_s_stream stream={0};
 assert(a6_s_codec_replay(&stream)==-EIO && transfers==1 && stream.failed_codec_reg==8);
 stream=(struct a6_s_stream){0};transfers=0;a6_s_raw_active=true;
 assert(!a6_s_codec_replay(&stream) && transfers==3 && stream.codec_dirty==3);
 assert(stream.replay_mismatches==1 && stream.mismatch_regs[0]==8 && stream.mismatch_want[0]==0x77 && stream.mismatch_got[0]==0x66);
 for(int i=0;i<3;i++){stream=(struct a6_s_stream){0};transfers=0;fail_transfer=i;assert(a6_s_codec_replay(&stream)==-ETIMEDOUT && stream.codec_dirty==(unsigned)i+1);}

}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'test.c';p.write_text(code);exe=Path(d)/'test'
 subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('PASS: raw bank isolation, bounded bursts, nonzero counts, occupancy pairs and bounded evidence buffers')

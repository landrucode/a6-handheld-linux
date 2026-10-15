#!/usr/bin/env python3
"""Test the exact codec clearing probe against W1C, RW and failing SPI models."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/platform/a6-audio-alsa.inc').read_text()
s=s[s.index('static int a6_s_codec_clear_probe('):s.index('static int a6_s_codec_restore(')]
code=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
typedef uint8_t u8;typedef uint32_t u32;
struct a6_s_stream {u8 clear_before[2],clear_write[2],clear_after[2],clear_final[2];unsigned clear_attempts;bool clear_io_error;};
static bool a6_s_raw_active=true,w1c=true;static unsigned calls,reads;static int fail_write=-1,fail_read=-1;static u8 values[2]={0x87,1},written[8];
static int a6_ac_transfer(u32 reg,u8 *reply,bool write,u8 value){unsigned slot=reg==0x4a ? 0 : 1;assert(write);written[calls]=value;if((int)calls++==fail_write)return -EIO;if(w1c)values[slot]&=~(value&(slot ? 1 : 0x80));else values[slot]=value;return 0;}
static int a6_ac_read_reg(u32 reg,u8 *reply){if((int)reads++==fail_read)return -EIO;reply[4]=values[reg==0x4a ? 0 : 1];return 0;}
'''+s+r'''
int main(void){struct a6_s_stream stream={0};
 assert(a6_s_codec_clear_probe(&stream,0x4a,7,0x87)==0);
 assert(stream.clear_after[0]==7 && stream.clear_final[0]==7 && calls==2 && written[0]==0x87 && written[1]==7);
 assert(a6_s_codec_clear_probe(&stream,0x4f,0,1)==0 && calls==4 && written[2]==1 && written[3]==0);
 assert(stream.clear_attempts==3);
 assert(a6_s_codec_clear_probe(&stream,0x4a,0x87,0x87)==-EUCLEAN && calls==4);
 assert(a6_s_codec_clear_probe(&stream,0x4a,7,0x97)==-EUCLEAN && calls==4);
 assert(a6_s_codec_clear_probe(&stream,0x4b,0,1)==-EUCLEAN && calls==4);
 a6_s_raw_active=false;assert(a6_s_codec_clear_probe(&stream,0x4a,7,0x87)==-EUCLEAN && calls==4);a6_s_raw_active=true;
 calls=reads=0;w1c=false;values[0]=0x87;
 assert(!a6_s_codec_clear_probe(&stream,0x4a,7,0x87) && values[0]==7 && calls==2);
 assert(stream.clear_after[0]==0x87 && stream.clear_final[0]==7);
 w1c=true;
 for(int i=0;i<2;i++){calls=reads=0;values[0]=0x87;fail_write=i;assert(a6_s_codec_clear_probe(&stream,0x4a,7,0x87)==-EUCLEAN && calls==2);}
 fail_write=-1;
 for(int i=0;i<2;i++){calls=reads=0;values[0]=0x87;fail_read=i;assert(a6_s_codec_clear_probe(&stream,0x4a,7,0x87)==-EUCLEAN && calls==2);}
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'clear.c';p.write_text(code);exe=Path(d)/'clear';subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
print('PASS: current-byte/expected-byte probe, W1C/RW observations, exact final restoration, exact mask restriction and SPI failure retention')

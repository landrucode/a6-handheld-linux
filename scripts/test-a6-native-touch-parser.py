#!/usr/bin/env python3
"""Compile the actual native poll parser with transport/input mocks."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'kernel/platform/a6-touch-native-input.inc').read_text()
poll = source[source.index('static int a6_native_poll(void)'):source.index('static void a6_native_worker')]
report = (ROOT / 'kernel/platform/a6-touch-report-probe.inc').read_text()
helpers = report[report.index('static void a6_report_checksum'):report.index('#ifdef A6_TOUCH_REPORT_METADATA\nstatic int')]
preamble = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <assert.h>
typedef uint8_t u8; typedef uint16_t u16; typedef int16_t s16;
#define clamp_t(type, value, lower, upper) mock_clamp((type)(value), (type)(lower), (type)(upper))
static int mock_clamp(int value, int lower, int upper) { return value < lower ? lower : value > upper ? upper : value; }
#define MT_TOOL_FINGER 0
#define ABS_MT_POSITION_X 0
#define ABS_MT_POSITION_Y 1
static unsigned get_unaligned_le16(const void *q) { const u8 *p=q; return p[0]|p[1]<<8; }
static void put_unaligned_le16(unsigned n, void *q) { u8 *p=q; p[0]=n; p[1]=n>>8; }
static u8 a6_native_tx[838], a6_native_rx[838], a6_native_sequence;
static unsigned a6_native_cs, a6_native_width=5000, a6_native_height=8900, a6_native_frames;
static unsigned a6_report_max_packet=838, emitted;
static unsigned a6_native_poll_cpu, a6_native_reply_cpu;
static unsigned raw_smp_processor_id(void) { return 0; }
static unsigned a6_native_stage, a6_native_wire_bytes, a6_native_atn, a6_native_idle_polls;
static unsigned a6_native_invalid_lengths, a6_native_empty_lengths;
static unsigned a6_native_coordinate_clamps;
static int current_slot, reported_x[10], reported_y[10];
static u8 a6_native_length_reply[16];
static void *a6_touch_gpio;
#define A6_TOUCH_ATN 0
static unsigned mock_atn=0x280;
static unsigned readl(void *address) { return mock_atn; }
static int a6_native_reject(int error) { return error; }
static void *a6_native_input;
static u8 fixture[91], length_reply[16];
static int a6_native_spi_xfer(const u8 *tx, unsigned n, u8 *rx, unsigned rn, unsigned cs) {
 if(n==16) memcpy(rx,length_reply,rn); else { assert(n==sizeof(fixture)); memcpy(rx,fixture,rn); } return 0;
}
static int input_mt_get_slot_by_key(void *d, int key) { return key%10; }
static void input_mt_slot(void *d, int slot) { current_slot=slot; emitted++; }
static bool input_mt_report_slot_state(void *d, int tool, bool valid) { return valid; }
static void input_report_abs(void *d, int code, int value) { if(code==ABS_MT_POSITION_X)reported_x[current_slot]=value; else reported_y[current_slot]=value; emitted++; }
static void input_mt_sync_frame(void *d) { emitted++; }
static void input_sync(void *d) { emitted++; }
'''
tests = r'''
static void checksum(void) {
 unsigned sum=0,i; for(i=5;i<89;i++)sum+=fixture[i]; put_unaligned_le16(sum,fixture+89);
}
static void setup(void) {
 memset(fixture,0,sizeof(fixture)); memset(length_reply,0,sizeof(length_reply));
 fixture[0]=0xea; fixture[1]=1; fixture[2]=86; fixture[4]=(u8)(-(0xea+1+86));
 fixture[5]=0x44; fixture[7]=24; fixture[21]=2; fixture[22]=30;
 fixture[29]=1; fixture[30]=3; fixture[59]=2; fixture[60]=4;
 put_unaligned_le16(123,fixture+33); put_unaligned_le16(456,fixture+35);
 put_unaligned_le16(789,fixture+63); put_unaligned_le16(1234,fixture+65);
 length_reply[0]=0xe1; length_reply[1]=86; a6_report_checksum(length_reply);
 checksum(); a6_native_sequence=1; emitted=0; mock_atn=0x280;
 a6_native_coordinate_clamps=0; memset(reported_x,0,sizeof(reported_x)); memset(reported_y,0,sizeof(reported_y));
}
static void reject(void) { assert(a6_native_poll()<0); assert(!emitted); }
int main(void) {
 setup(); assert(!a6_native_poll()); assert(emitted==8); assert(a6_native_sequence==2);
 setup(); fixture[59]=1; checksum(); reject();
 setup(); fixture[21]=11; checksum(); reject();
 setup(); fixture[22]=29; checksum(); reject();
 setup(); fixture[7]=255; checksum(); reject();
 setup(); put_unaligned_le16(5001,fixture+33); checksum(); assert(!a6_native_poll()); assert(reported_x[1]==5000); assert(a6_native_coordinate_clamps==1);
 setup(); put_unaligned_le16(8901,fixture+35); checksum(); assert(!a6_native_poll()); assert(reported_y[1]==8900); assert(a6_native_coordinate_clamps==1);
 setup(); put_unaligned_le16((u16)-81,fixture+33); put_unaligned_le16((u16)-66,fixture+35); checksum(); assert(!a6_native_poll()); assert(emitted==8); assert(reported_x[1]==0 && reported_y[1]==0); assert(a6_native_coordinate_clamps==2);
 setup(); put_unaligned_le16(32767,fixture+33); put_unaligned_le16(32768,fixture+35); checksum(); assert(!a6_native_poll()); assert(reported_x[1]==5000 && reported_y[1]==0); assert(a6_native_coordinate_clamps==2);
 setup(); fixture[40]^=1; reject();
 setup(); fixture[1]=2; reject();
 setup(); put_unaligned_le16(839,length_reply+1); a6_report_checksum(length_reply); reject();
 setup(); length_reply[15]^=1; assert(a6_native_poll()==-EAGAIN); assert(!emitted); assert(a6_native_invalid_lengths==1);
 setup(); length_reply[1]=0; a6_report_checksum(length_reply); assert(!a6_native_poll()); assert(!emitted); assert(a6_native_empty_lengths==1);
 setup(); mock_atn=0x281; assert(!a6_native_poll()); assert(!emitted); assert(a6_native_idle_polls==1);
 puts("PASS actual native parser: two contacts, sequence, empty poll, duplicate IDs, packet bounds, signed edge clamping and checksums");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-native-parser-') as folder:
    c = Path(folder) / 'test.c'
    executable = Path(folder) / 'test'
    c.write_text(preamble + helpers + poll + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-fsanitize=address,undefined',
                    str(c), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)

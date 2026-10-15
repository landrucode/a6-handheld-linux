#!/usr/bin/env python3
"""Exercise the actual bounded PIO transfer against a FIFO/count simulator."""
from pathlib import Path
import subprocess
import tempfile


root = Path(__file__).resolve().parent.parent
source = (root / 'kernel/platform/a6-touch-fw-upload.inc').read_text()
body = source[source.index('#define A6_FW_PACKET_BYTES'):
              source.index('static ssize_t a6_fw_status_show')]
mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define A6_TOUCH_NATIVE_INPUT 1
#define A6_TOUCH_REPORT_METADATA 1
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define A6_TOUCH_ATN 0x10
#define A6_TOUCH_RESET 0x14
typedef uint64_t u64;
static unsigned raw_smp_processor_id(void) {return 0;}
typedef uint8_t u8;
typedef uint32_t u32;
#define U32_MAX UINT32_MAX
#define A6_TOUCH_CS 0xc4
static unsigned char spi[0x1000], gpio[0x1000];
static unsigned char *a6_touch_spi=spi,*a6_touch_gpio=gpio;
static unsigned long jiffies;
static u64 mock_us;
static u64 ktime_get_ns(void) {return mock_us*1000;}
static unsigned sent_bytes, received_bytes, tx_left, rx_left, fifo_count;
static unsigned tx_fifo_count, rx_generated;
static u8 fifo[16], transmit_first[16];
static int stall, bad_status;
static u32 readl(const void *ptr) {
 const unsigned char *p=ptr;
 if(p>=spi && p<spi+sizeof(spi)) {
  unsigned off=(unsigned)(p-spi);
  if(off==8) {
   if(bad_status)return UINT32_MAX;
   if(!stall)for(unsigned i=0;i<16 && tx_fifo_count;i++) {
    --tx_fifo_count;--tx_left;
    if(rx_left && fifo_count<16)
     fifo[fifo_count++]=(++rx_generated==1?0x4b:0xc1);
   }
   return (tx_fifo_count<<6)|(fifo_count<<11);
  }
  if(off==0x4c) return tx_left;
  if(off==0x34) return rx_left;
  if(off==0x20) {
   assert(fifo_count && rx_left);
   u8 result=fifo[0];memmove(fifo,fifo+1,--fifo_count);
   --rx_left;++received_bytes;return result;
  }
  u32 result;memcpy(&result,p,4);return result;
 }
 u32 result;memcpy(&result,p,4);return result;
}
static void writel(u32 value,void *ptr) {
 unsigned char *p=ptr;
 if(p>=spi && p<spi+sizeof(spi)) {
  unsigned off=(unsigned)(p-spi);
  if(off==0) { if(value==0) fifo_count=tx_fifo_count=0; memcpy(p,&value,4);return; }
  if(off==0x4c) {tx_left=value;memcpy(p,&value,4);return;}
  if(off==0x34) {rx_left=value;memcpy(p,&value,4);return;}
  if(off==0x10) {
   assert(tx_left>tx_fifo_count && tx_fifo_count<16 && sent_bytes<64340);
   if(sent_bytes<16)transmit_first[sent_bytes]=value;
   ++tx_fifo_count;++sent_bytes;
   return;
  }
 }
 memcpy(p,&value,4);
}
static unsigned long msecs_to_jiffies(unsigned x) {return x;}
static int time_after(unsigned long a,unsigned long b) {return a>b;}
static void usleep_range(unsigned a,unsigned b) {(void)a;(void)b;mock_us+=10000;jiffies=mock_us/1000;}
static void cond_resched(void) {}
static void udelay(unsigned n) {mock_us+=n;jiffies=mock_us/1000;}
'''
tests = r'''
static void reset_mock(void) {
 memset(spi,0,sizeof(spi));memset(gpio,0,sizeof(gpio));
 memset(fifo,0,sizeof(fifo));memset(transmit_first,0,sizeof(transmit_first));
 sent_bytes=received_bytes=tx_left=rx_left=fifo_count=0;
 tx_fifo_count=rx_generated=0;
 jiffies=0;mock_us=0;stall=bad_status=0;
}
int main(void) {
 static u8 packet[64340], rx[838];
 for(unsigned i=0;i<sizeof(packet);i++)packet[i]=i&255;
 reset_mock();
 assert(a6_fw_spi_xfer(packet,sizeof(packet),NULL,0,90000,0x202)==0);
 assert(sent_bytes==sizeof(packet) && a6_fw_sent==sizeof(packet));
 assert(!memcmp(transmit_first,packet,16));
 assert(readl(gpio+A6_TOUCH_CS)==0x203 && !readl(spi));
 reset_mock();
 assert(a6_fw_spi_xfer(packet,2,rx,2,2000,0x202)==0);
 assert(sent_bytes==2 && received_bytes==2 && rx[0]==0x4b && rx[1]==0xc1);
 assert(readl(gpio+A6_TOUCH_CS)==0x203);
 reset_mock();stall=1;
 assert(a6_fw_spi_xfer(packet,32,NULL,0,2,0x202)==-ETIMEDOUT);
 assert(sent_bytes<=16 && readl(gpio+A6_TOUCH_CS)==0x203 && !readl(spi));
 reset_mock();bad_status=1;
 assert(a6_fw_spi_xfer(packet,32,NULL,0,2,0x202)==-EIO);
 assert(readl(gpio+A6_TOUCH_CS)==0x203 && !readl(spi));
 /* Model the observed periodic-tick sleep per FIFO refill: old deadline
  * fails a 181-byte frame. This is a scheduling model, not an A6 clock model. */
 reset_mock();
 assert(a6_fw_spi_xfer(packet,181,rx,181,100,0x202)==-ETIMEDOUT);
 assert(received_bytes<181 && readl(gpio+A6_TOUCH_CS)==0x203 && !readl(spi));
 reset_mock(); a6_touch_trace_begin();
 assert(a6_native_spi_xfer(packet,181,rx,181,0x202)==0);
 assert(received_bytes==181 && a6_touch_last_transfer.received==181);
 assert(a6_touch_last_transfer.sent==181 && !a6_touch_last_transfer.rx_remaining);
 reset_mock();
 assert(a6_native_spi_xfer(packet,838,rx,838,0x202)==0);
 assert(received_bytes==838);
 reset_mock(); stall=1;
 assert(a6_native_spi_xfer(packet,838,rx,838,0x202)==-ETIMEDOUT);
 assert(jiffies<=631 && a6_touch_last_transfer.result==-ETIMEDOUT);
 assert(a6_touch_last_transfer.sent==16 && !a6_touch_last_transfer.received);
 assert(a6_touch_last_transfer.tx_remaining==838 && a6_touch_last_transfer.rx_remaining==838);
 assert(readl(gpio+A6_TOUCH_CS)==0x203 && !readl(spi));
 reset_mock(); bad_status=1;
 assert(a6_native_spi_xfer(packet,181,rx,181,0x202)==-EIO);
 assert(readl(gpio+A6_TOUCH_CS)==0x203 && !readl(spi));
 reset_mock();
 assert(a6_native_spi_xfer(packet,839,rx,839,0x202)==-EINVAL);
 assert(!sent_bytes);
 puts("PASS: firmware path; tick-sleep frame regression; native 181/838-byte transfers; bounded stall/fault cleanup and frozen counters");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-fw-pio-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(mock + body + tests)
    subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-variable', '-Wno-unused-function',
                    '-fsanitize=undefined', str(path / 'test.c'), '-o',
                    str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)

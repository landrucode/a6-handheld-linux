#!/usr/bin/env python3
"""Compile the actual kernel packet encoders and compare fixed N1 wire bytes."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'kernel/platform/a6-touch-post-upload.inc').read_text()
start = source.index('static void a6_post_word(')
end = source.index('static int a6_post_read(', start)
helpers = source[start:end]
test = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
''' + helpers + r'''
static void print_packet(const u8 *data, unsigned int length)
{
    unsigned int i;
    for (i = 0; i < length; i++)
        printf("%02x", data[i]);
    putchar('\n');
}
static void read_packet(u32 addr)
{
    u8 packet[8] = {0x1c, 0x73};
    a6_post_word(packet + 2, addr);
    a6_post_sum(packet, 4);
    print_packet(packet, sizeof(packet));
}
static void write_packet(u32 addr, u32 value)
{
    u8 packet[16] = {0x1e, 0x33};
    a6_post_word(packet + 2, addr);
    a6_post_word(packet + 6, UINT32_MAX);
    a6_post_word(packet + 10, value);
    a6_post_sum(packet, 12);
    print_packet(packet, sizeof(packet));
}
int main(void)
{
    u8 final[12] = {0x1d, 0x53};
    read_packet(0x10008ffc);
    write_packet(0x000016e4, 0x1000300c);
    write_packet(0x1000305c, 0x20);
    write_packet(0x10003058, 6);
    write_packet(0x10003000, 3);
    write_packet(0x10003000, 2);
    write_packet(0x10003518, 1);
    read_packet(0x10003800);
    a6_post_word(final + 2, 0x10001800);
    final[7] = 1;
    a6_post_sum(final, 8);
    print_packet(final, sizeof(final));
    a6_post_word(final + 2, 0x10003400);
    a6_post_sum(final, 8);
    print_packet(final, sizeof(final));
    return 0;
}
'''
expected = [
    '1c738ffc1000019b',
    '1e3316e40000ffffffff300c10000542',
    '1e33305c1000ffffffff0020000004b8',
    '1e3330581000ffffffff00060000049a',
    '1e3330001000ffffffff00030000043f',
    '1e3330001000ffffffff00020000043e',
    '1e3335181000ffffffff00010000045a',
    '1c73380010000048',
    '1d5318001000000100000029',
    '1d5334001000000100000045',
]
with tempfile.TemporaryDirectory(prefix='a6-touch-post-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(test)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=undefined', str(path / 'test.c'),
                    '-o', str(path / 'test')], check=True)
    actual = subprocess.check_output([str(path / 'test')], text=True).splitlines()
assert actual == expected, (actual, expected)
print('PASS: actual C emits the ten fixed N1 read/write/final packets')

#!/usr/bin/env python3
"""Exercise the generated native C event loop with queued and interrupted I/O."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
s = (root/'build/wvkbd-src-bottom/main.c').read_text()
a = s.index('    while (run_display) {')
b = s.index('        if (fds[WAYLAND_FD].revents & POLLERR)', a)
loop = s[a:b] + '    }\n'
die_macro = s[s.index('#define die('):s.index('/* array size */')]
harness = r'''
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
static int run_display, pending, prepared, reads, cancels, prepares, polls, flushes, mode;
#define die(...) abort()
static int wl_display_prepare_read(void *d) {
 if (pending) {errno=EAGAIN; return -1;}
 assert(!prepared); prepared=1; prepares++; return 0;
}
static int wl_display_dispatch_pending(void *d) {
 pending=0; if(reads)run_display=0; return 0;
}
static void wl_display_cancel_read(void *d) {
 assert(prepared); prepared=0; cancels++;
}
static int wl_display_read_events(void *d) {
 assert(prepared); prepared=0; reads++; pending=1; return 0;
}
static int wl_display_flush(void *d) {
 flushes++; if(mode==2 && flushes==1){errno=EAGAIN;return -1;} return 0;
}
static int fake_poll(struct pollfd *fds, unsigned long n, int timeout) {
 assert(!pending && prepared && flushes); polls++;
 fds[0].revents=fds[1].revents=0;
 if(mode==1 && polls==1){errno=EINTR;return -1;}
 if(mode==2 && polls==1){assert(fds[0].events&POLLOUT);fds[0].revents=POLLOUT;return 1;}
 if(mode==3 && polls==1){fds[1].revents=POLLIN;return 1;}
 fds[0].revents=POLLIN;return 1;
}
#define poll fake_poll
static void trial(void) {
 void *display=NULL; struct pollfd fds[2]={{0}}; int WAYLAND_FD=0;
'''
harness = harness.replace('#define die(...) abort()', die_macro)
harness += loop + r'''
 assert(!prepared && reads==1 && prepares==reads+cancels);
}
int main(void) {
 for(mode=0;mode<4;mode++) {
  run_display=1; pending=1; prepared=reads=cancels=prepares=polls=flushes=0;
  trial();
 }
 puts("Actual C poll loop passed: buffered events, EINTR, output backpressure, signal-only wakeup");
}
'''
with tempfile.TemporaryDirectory(prefix='a6-wvkbd-poll-') as d:
 p=Path(d)/'test.c';p.write_text(harness)
 subprocess.run(['cc','-std=c11','-Werror=implicit-function-declaration',str(p),'-o',str(Path(d)/'test')],check=True)
 subprocess.run([str(Path(d)/'test')],check=True)
 # Negative control: the original unbraced multi-statement macro exits
 # even on a successful pending dispatch. This must be detected.
 broken = harness.replace(die_macro, '#define die(...) fprintf(stderr, __VA_ARGS__); exit(1)\n')
 assert broken != harness
 p.write_text(broken)
 subprocess.run(['cc','-std=c11',str(p),'-o',str(Path(d)/'broken')],check=True)
 result = subprocess.run([str(Path(d)/'broken')],capture_output=True)
 assert result.returncode == 1, 'original exit regression was not detected'
 print('Negative control caught the original die macro unconditional exit')

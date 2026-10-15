#!/usr/bin/env python3
"""Send bounded US-keyboard or relative pointer events through USB SSH/uinput.

Requires a6-uinput and labels before Weston enumeration. Input goes to the
focused Wayland client. --enter executes typed text if that client is a shell.
"""
import argparse
from pathlib import Path
import struct
import subprocess
import time
import fcntl

parser=argparse.ArgumentParser(description=__doc__)
actions=parser.add_mutually_exclusive_group(required=True)
actions.add_argument('--text')
actions.add_argument('--key',choices=['Return','Tab','Escape','BackSpace','Up','Down','Left','Right','ctrl+c','ctrl+d','ctrl+l','ctrl+o','ctrl+x'])
actions.add_argument('--move',nargs=2,type=int,metavar=('DX','DY'))
actions.add_argument('--click',choices=['left','middle','right'])
actions.add_argument('--scroll',type=int)
parser.add_argument('--enter',action='store_true')
parser.add_argument('--event-delay-ms',type=int,default=50,
                    help='pace events for the software compositor (20..200, default50)')
args=parser.parse_args()
if not 20<=args.event_delay_ms<=200:parser.error('event delay must be20..200ms')
if args.enter and args.text is None:parser.error('--enter requires --text')
events=[]
def event(device,kind,code,value):events.append(struct.pack('<IIIi',device,kind,code,value))
def key(code,modifier=None):
    if modifier:event(0,1,modifier,1)
    event(0,1,code,1);event(0,1,code,0)
    if modifier:event(0,1,modifier,0)
if args.text is not None:
    if not 0<len(args.text)<=256 or any(not 32<=ord(c)<=126 for c in args.text):parser.error('text must be1..256 printable ASCII characters')
    mapping={}
    for chars,codes in [('1234567890',range(2,12)),('qwertyuiop',range(16,26)),('asdfghjkl',range(30,39)),('zxcvbnm',range(44,51))]:
        mapping.update(zip(chars,codes))
    mapping.update({' ':57,'-':12,'=':13,'[':26,']':27,';':39,"'":40,'`':41,'\\':43,',':51,'.':52,'/':53})
    shifted=dict(zip('!@#$%^&*()_+{}:"~|<>?', '1234567890-=[];\'`\\,./'))
    for char in args.text:
        upper='A'<=char<='Z'
        base=char.lower() if upper else shifted.get(char,char)
        key(mapping[base],42 if upper or char in shifted else None)
    if args.enter:key(28)
elif args.key:
    codes={'Return':28,'Tab':15,'Escape':1,'BackSpace':14,'Up':103,'Down':108,'Left':105,'Right':106,'ctrl+c':46,'ctrl+d':32,'ctrl+l':38,'ctrl+o':24,'ctrl+x':45}
    key(codes[args.key],29 if args.key.startswith('ctrl+') else None)
elif args.move:
    if any(abs(v)>2048 for v in args.move):parser.error('each relative motion must be between-2048 and2048')
    for code,value in enumerate(args.move):event(1,2,code,value)
elif args.click:
    code={'left':0x110,'right':0x111,'middle':0x112}[args.click]
    event(1,1,code,1);event(1,1,code,0)
else:
    if not -20<=args.scroll<=20:parser.error('scroll must be between-20 and20')
    event(1,2,8,args.scroll)
# Keep input below the small evdev queue capacity on the single A6 CPU.
# Serialize host invocations and pace each event; do not retry unknown input.
repo=Path(__file__).resolve().parents[1]
with (repo/'build/a6-drm-input.lock').open('w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
    process=subprocess.Popen([str(repo/'scripts/a6-ssh'),
        f"test -p /tmp/a6-input-events && timeout {max(30,int(len(events)*args.event_delay_ms/1000)+10)} /bin/bash -c 'cat > /tmp/a6-input-events'"],stdin=subprocess.PIPE)
    try:
        for record in events:
            process.stdin.write(record)
            process.stdin.flush()
            time.sleep(args.event_delay_ms/1000)
        process.stdin.close()
        code=process.wait(timeout=10)
        if code:raise subprocess.CalledProcessError(code,process.args)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
print('Sent paced events through USB SSH/uinput; verify the focused application result.')

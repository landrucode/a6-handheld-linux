#!/usr/bin/env python3
"""Stage the compressed desktop base into phone RAM, mount overlay and zram.

No NAND, persistent writes, reboot or desktop/network launch. Root image stays
compressed; test mounts live under /mnt/a6-ram. All services are temporary USB.
"""
from pathlib import Path
import hashlib,importlib.util,re,secrets,socket,time
ROOT=Path(__file__).resolve().parents[1]
def main():
 spec=importlib.util.spec_from_file_location('serial',ROOT/'scripts/a6-capture-wifi-ehci-enum.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 image=ROOT/'build/arch-bootstrap/arch-hyprland-user-desktop.squashfs';digest=hashlib.sha256(image.read_bytes()).hexdigest()
 nonce=secrets.token_hex(4);dest='/tmp/a6-base.squashfs';status='/tmp/a6-base-'+nonce+'.status';evidence=[]
 def serial(c,timeout=20):
  r=m.serial(c,timeout=timeout);evidence.append(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError('USB root-stage command failed')
  return r.stdout.replace('\r','')
 try:
  s=serial('busybox grep -E "squashfs|overlay" /proc/filesystems; test -b /dev/loop0 && echo LOOP_OK; test -b /dev/zram0 && echo ZRAM_OK; busybox grep MemAvailable /proc/meminfo')
  if 'squashfs' not in s or 'overlay' not in s or 'LOOP_OK' not in s:raise RuntimeError('combined RAM-root features absent')
  extent=serial('if test -f '+dest+'; then printf BASE_BYTES=; busybox stat -c %s '+dest+'; else echo BASE_BYTES=0; fi')
  match=re.search(r'(?m)^BASE_BYTES=(\d+)$',extent)
  if not match:raise RuntimeError('RAM base extent unavailable')
  offset=int(match[1])
  if offset>image.stat().st_size:raise RuntimeError('RAM base larger than pinned image')
  worker='umask 077; busybox timeout 180 busybox nc -l -p 8084 '+('>> ' if offset else '> ')+dest+'; echo $? > '+status
  serial("busybox setsid busybox sh -c '"+worker+"' </dev/null >/tmp/a6-base-listener.log 2>&1 & echo BASE_LISTENING")
  deadline=time.monotonic()+5
  while True:
   try:connection=socket.create_connection(('192.168.7.2',8084),timeout=2);break
   except ConnectionRefusedError:
    if time.monotonic()>deadline:raise
    time.sleep(.1)
  with connection,image.open('rb') as src:
   connection.settimeout(30);src.seek(offset);sent=offset;next_report=((offset//(16*1024*1024))+1)*16*1024*1024
   while chunk:=src.read(65536):
    connection.sendall(chunk);sent+=len(chunk);time.sleep(.0625)
    if sent>=next_report:print('Compressed base sent:',sent//1024//1024,'MiB',flush=True);next_report+=16*1024*1024
   connection.shutdown(socket.SHUT_WR)
  s=serial('sleep 1; test "$(cat '+status+')" = 0 && '+"printf '%s  %s\\n' '"+digest+"' "+dest+' | busybox sha256sum -c - && echo BASE_VERIFIED',timeout=30)
  if 'BASE_VERIFIED\n' not in s:raise RuntimeError('RAM base hash mismatch')
  cmd=('busybox mkdir -p /mnt/a6-ram/base /mnt/a6-ram/writable /mnt/a6-ram/root; '
       'busybox mount -t squashfs -o ro,loop /tmp/a6-base.squashfs /mnt/a6-ram/base && '
       'busybox mount -t tmpfs -o size=128m tmpfs /mnt/a6-ram/writable && '
       'busybox mkdir -p /mnt/a6-ram/writable/upper /mnt/a6-ram/writable/work && '
       'busybox mount -t overlay overlay -o lowerdir=/mnt/a6-ram/base,upperdir=/mnt/a6-ram/writable/upper,workdir=/mnt/a6-ram/writable/work /mnt/a6-ram/root && '
       'echo RAM_OVERLAY_OK; '
       'printf RAM_OVERLAY_PROOF > /mnt/a6-ram/root/.a6-write-check && '
       'test -f /mnt/a6-ram/writable/upper/.a6-write-check && '
       'test ! -e /mnt/a6-ram/base/.a6-write-check && '
       'busybox rm /mnt/a6-ram/root/.a6-write-check && echo OVERLAY_WRITE_OK; '
       'if test -b /dev/zram0; then echo 134217728 > /sys/block/zram0/disksize; busybox mkswap /dev/zram0 && busybox swapon /dev/zram0 && echo ZRAM_SWAP_OK; fi; '
       'busybox grep -E "a6-ram|zram" /proc/mounts /proc/swaps; busybox grep MemAvailable /proc/meminfo')
  s=serial(cmd)
  if 'RAM_OVERLAY_OK\n' not in s:raise RuntimeError('RAM overlay mount failed')
  if 'OVERLAY_WRITE_OK\n' not in s:raise RuntimeError('RAM overlay write check failed')
  print('Compressed SquashFS + writable overlay mounted in RAM; '+('zram enabled' if 'ZRAM_SWAP_OK\n' in s else 'zram not enabled'))
 finally:
  p=ROOT/'build/session-logs'/('ram-base-stage-'+nonce+'.log');p.write_text('\n'.join(evidence));p.chmod(0o600)
if __name__=='__main__':main()

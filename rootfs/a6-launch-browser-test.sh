#!/bin/sh
# Mount the verified staged runtime and isolate Epiphany, retaining recovery outside it.
set -eu
bb=/bin/busybox
root=/tmp/graphics-runtime
groups=/tmp/a6-cgroup
$bb sh /tmp/a6-browser-extra-swap.sh
runtime=$root/opt/a6/browser-runtime
test -r /tmp/a6-browser-images/browser.squashfs
test -x "$root/bin/bash"
# Refuse a second launch before changing the current workload or observer.
if test -e "$groups/browser/cgroup.procs"; then
 test -z "$(cat "$groups/browser/cgroup.procs")"
fi
# Explicit diagnostic option: avoid swapping compressed image bytes into zram.
if test "${A6_BROWSER_PIN_IMAGES:-0}" = 1; then
 test -x /tmp/a6-pin-compressed-images
 resident=0
 if test -r /tmp/a6-pin-images.pid; then
  read -r pid </tmp/a6-pin-images.pid
  case "$pid" in ''|*[!0-9]*) exit 1;; esac
  if test -r /proc/$pid/cmdline && $bb tr '\000' ' ' </proc/$pid/cmdline | $bb grep -q '^/tmp/a6-pin-compressed-images '; then resident=1; fi
 fi
 if test "$resident" = 0; then
  (umask 077; : >/tmp/a6-pin-images.private.log; $bb setsid /tmp/a6-pin-compressed-images </dev/null >/tmp/a6-pin-images.private.log 2>&1 & echo $! >/tmp/a6-pin-images.pid)
 fi
 n=0
 until $bb grep -q '^COMPRESSED_IMAGES_RESIDENT$' /tmp/a6-pin-images.private.log; do
  n=$((n+1)); test "$n" -lt 15; $bb sleep 1
 done
fi
# The original minimal desktop resolved only /etc/hosts. Enable normal DNS.
$bb sed -i 's/^hosts:.*/hosts: files dns/' "$root/etc/nsswitch.conf"
$bb chmod 644 "$root/etc/nsswitch.conf"
# Retire only the observer from the preceding explicit launch.
if test -r /tmp/a6-browser-memory-watch.pid; then
 read -r observer </tmp/a6-browser-memory-watch.pid
 case "$observer" in ''|*[!0-9]*) exit 1;; esac
 if test -r /proc/$observer/cmdline && $bb tr '\000' ' ' </proc/$observer/cmdline | $bb grep -q '^/bin/busybox sh /tmp/a6-browser-memory-watch.sh '; then
  kill "$observer"
 fi
fi
if test -e "$groups/browser/cgroup.procs"; then
 test -z "$(cat "$groups/browser/cgroup.procs")"
 $bb rmdir "$groups/browser"
fi
$bb mkdir -p "$groups" "$runtime"
if ! $bb grep -q " $groups cgroup2 " /proc/mounts; then
 $bb mount -t cgroup2 none "$groups"
fi
echo +memory >"$groups/cgroup.subtree_control"
$bb mkdir "$groups/browser"
available_ram=$($bb awk '/^MemTotal:/ {print $2}' /proc/meminfo)
if test "$available_ram" -ge 900000; then
 # Keep room for the compositor, keyboard and pinned compressed images.
 if test -f "$root/usr/local/share/a6/compositor" && test "$(cat "$root/usr/local/share/a6/compositor")" = labwc; then
  # The smaller Pixman desktop leaves room for the browser's cold working set.
  echo 536870912 >"$groups/browser/memory.high"
  echo 603979776 >"$groups/browser/memory.max"
 else
  echo 469762048 >"$groups/browser/memory.high"
  echo 536870912 >"$groups/browser/memory.max"
 fi
else
 echo 335544320 >"$groups/browser/memory.high"
 echo 402653184 >"$groups/browser/memory.max"
fi
echo 134217728 >"$groups/browser/memory.swap.max"
echo 1 >"$groups/browser/memory.oom.group"
if ! $bb grep -q " $runtime squashfs " /proc/mounts; then
 $bb mount -t squashfs -o loop,ro /tmp/a6-browser-images/browser.squashfs "$runtime"
fi
$bb mkdir -p "$root/usr/local/lib/a6-browser"
$bb cp /bin/busybox "$root/usr/local/lib/a6-browser/busybox"
$bb chmod 755 "$root/usr/local/lib" "$root/usr/local/lib/a6-browser" "$root/usr/local/lib/a6-browser/busybox"
# This worker alone enters the group; the caller and observers remain outside.
$bb setsid $bb sh -c '
 echo $$ >/tmp/a6-cgroup/browser/cgroup.procs
 exec /bin/busybox unshare -m /bin/busybox sh /tmp/a6-browser-enter-root.sh
' </dev/null >/tmp/a6-browser.private.log 2>&1 &
$bb sleep 1
# Optional evidence collector only; upstream oomd supplies the kill policy.
if test "${A6_BROWSER_OBSERVE:-0}" = 1; then
 $bb setsid $bb sh /tmp/a6-browser-memory-watch.sh </dev/null >/dev/null 2>&1 &
 echo $! >/tmp/a6-browser-memory-watch.pid
fi
echo BROWSER_LAUNCH_REQUESTED

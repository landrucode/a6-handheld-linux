#!/bin/sh
# Protect interactive services and isolate RAM profile/buffer storage.
set -eu
bb=/bin/busybox
root=/tmp/graphics-runtime
groups=/tmp/a6-cgroup
if test "${1:-prepare}" = enter; then
 shift
 test -d "$groups/desktop"
 echo $$ >"$groups/desktop/cgroup.procs"
 exec "$@"
fi
test "${1:-prepare}" = prepare
test "$(id -u)" = 0
$bb mkdir -p "$groups"
if ! $bb grep -q " $groups cgroup2 " /proc/mounts; then $bb mount -t cgroup2 none "$groups"; fi
echo +memory >"$groups/cgroup.subtree_control"
$bb mkdir -p "$groups/desktop"
# Reclaim protection, not a hard desktop memory limit. Browser stays a sibling.
echo 201326592 >"$groups/desktop/memory.low"
echo 67108864 >"$groups/desktop/memory.min"
echo 33554432 >"$groups/desktop/memory.swap.max"
# Run before Wayland/audio sockets exist; never hide a running session.
$bb mkdir -p "$root/run/user/1000" "$root/home/a6/browser"
if ! $bb grep -q " $root/run/user/1000 tmpfs " /proc/mounts; then
 test ! -S "$root/run/user/1000/wayland-1"
 $bb mount -t tmpfs -o size=32m,mode=0700,uid=1000,gid=1000,nosuid,nodev tmpfs "$root/run/user/1000"
fi
if ! $bb grep -q " $root/home/a6/browser tmpfs " /proc/mounts; then
 # Fresh RAM roots only. A live profile migration is a separate attended fix.
 test -z "$(ls -A "$root/home/a6/browser")"
 $bb mount -t tmpfs -o size=256m,mode=0700,uid=1000,gid=1000,nosuid,nodev tmpfs "$root/home/a6/browser"
fi
echo A6_DESKTOP_MEMORY_READY

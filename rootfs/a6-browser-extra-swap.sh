#!/bin/sh
# Browser-only opt-in capacity; keep the original desktop swap and power guards.
set -eu
bb=/bin/busybox
marker=/tmp/a6-browser-zram.id
if test -f "$marker"; then
 read -r id <"$marker"
 case "$id" in ''|*[!0-9]*) exit 1;; esac
 $bb grep -q "^/dev/zram$id " /proc/swaps
 exit 0
fi
test -r /sys/class/zram-control/hot_add
id=$(cat /sys/class/zram-control/hot_add)
test "$id" -ge 1 && test "$id" -le 7
echo 268435456 >"/sys/block/zram$id/disksize"
$bb mkswap "/dev/zram$id" >/dev/null
$bb swapon "/dev/zram$id"
umask 077
printf '%s\n' "$id" >"$marker"

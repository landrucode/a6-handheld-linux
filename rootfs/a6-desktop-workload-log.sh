#!/bin/sh
# Bounded, read-only performance journal. No argv, pages, network names or secrets.
set -eu
bb=/bin/busybox
umask 077
log=/tmp/a6-desktop-workload.private.log
exec >"$log" 2>&1
n=0
while test "$n" -lt 144; do
 echo SAMPLE=$n
 cat /proc/uptime
 $bb grep -E '^(MemAvailable|SwapFree|Shmem|Mlocked):' /proc/meminfo
 cat /proc/pressure/cpu /proc/pressure/memory
 test ! -r /sys/firmware/a6_touch_native/status || $bb head -n 1 /sys/firmware/a6_touch_native/status
 $bb head -n 1 /proc/stat
 for group in desktop browser; do
  echo GROUP=$group
  for field in memory.current memory.swap.current memory.events memory.pressure; do
   test ! -r "/tmp/a6-cgroup/$group/$field" || cat "/tmp/a6-cgroup/$group/$field"
  done
 done
 for f in /proc/[0-9]*/comm; do
  # /proc entries may vanish between expansion and open. A subshell keeps
  # a failed redirection from terminating this set -e journal.
  name=$(cat "$f" 2>/dev/null) || continue
  case "$name" in Hyprland|labwc|epiphany|foot|wvkbd-native|a6-app-panel|a6-labwc-panel)
   pid=${f#/proc/};pid=${pid%/comm}
   echo PROCESS=$name PID=$pid
   $bb awk '{sub(/^.*\) /, ""); print "minor_faults=" $8,"major_faults=" $10,"user_ticks=" $12,"system_ticks=" $13,"rss_pages=" $22}' "/proc/$pid/stat" || :
   $bb grep -E '^(Rss|Pss|Swap|Locked):' "/proc/$pid/smaps_rollup" || :
   ;;
  esac
 done
 n=$((n+1));$bb sleep 5
done
echo A6_DESKTOP_WORKLOAD_COMPLETE

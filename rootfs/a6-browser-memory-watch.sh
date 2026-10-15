#!/bin/sh
# Observe only the isolated browser workload; never cycle USB or the radio.
set -eu
bb=/bin/busybox
group=/tmp/a6-cgroup/browser
test -r "$group/cgroup.procs"
umask 077
exec >"${1:-/tmp/a6-browser-memory.private.log}" 2>&1
printf 'uptime_seconds mem_available_kb browser_bytes browser_peak_bytes swap_bytes pss_kb pgmajfault pswpin pswpout\n'
n=0
while test "$n" -lt 300; do
 available=$($bb awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
 current=$(cat "$group/memory.current")
 peak=$(cat "$group/memory.peak")
 swap=$(cat "$group/memory.swap.current")
 pss=0
 for pid in $(cat "$group/cgroup.procs"); do
  value=$($bb awk '/^Pss:/ {print $2}' /proc/$pid/smaps_rollup 2>/dev/null || :)
  pss=$((pss+${value:-0}))
 done
 counters=$($bb awk '$1=="pgmajfault" || $1=="pswpin" || $1=="pswpout" {v[$1]=$2} END {printf "%s %s %s",v["pgmajfault"],v["pswpin"],v["pswpout"]}' /proc/vmstat)
 printf '%s %s %s %s %s %s %s\n' "$($bb awk '{print $1}' /proc/uptime)" "$available" "$current" "$peak" "$swap" "$pss" "$counters"
 printf 'memory_events '; $bb tr '\n' ' ' <"$group/memory.events"; printf '\n'
 printf 'pressure '; $bb tr '\n' ' ' </proc/pressure/memory; printf '\n'
 for zramfile in /sys/block/zram*/mm_stat; do
  device=${zramfile%/mm_stat}; device=${device##*/}
  printf 'zram %s ' "$device"; cat "$zramfile"
 done
 test -n "$(cat "$group/cgroup.procs")" || { echo BROWSER_WORKLOAD_ENDED; exit 0; }
 n=$((n+1)); $bb sleep 2
done
echo BROWSER_OBSERVATION_DEADLINE

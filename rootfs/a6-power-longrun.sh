#!/bin/sh
# Phone-local, bounded RAM journal; independent of USB and desktop processes.
# No SSIDs, MACs, credentials or argv. RAM survives link loss, not power loss.
set -u
umask 077
bb=/bin/busybox
log=/tmp/a6-power-longrun.log
pidfile=/tmp/a6-power-longrun.pid
if test -s "$pidfile"; then
 read old <"$pidfile"
 case "$old" in ''|*[!0-9]*) exit 1;; esac
 if test -r /proc/$old/cmdline && $bb tr '\000' ' ' </proc/$old/cmdline | $bb grep -q 'sh /tmp/a6-power-longrun.sh'; then exit 0; fi
fi
echo $$ >"$pidfile"
trap 'test -z "${probe:-}" || kill "$probe" 2>/dev/null || :; rm -f "$pidfile"; exit 0' HUP INT TERM
sample=0
probe=
probe_file=/tmp/a6-power-probe.private.log
while :; do
 if test -f "$log" && test "$($bb stat -c %s "$log")" -ge 2097152; then
  $bb mv "$log" "$log.previous"
 fi
 {
  printf '\nA6_POWER_SAMPLE=%s utc=' "$sample"
  $bb date -u +%Y-%m-%dT%H:%M:%SZ
  printf 'uptime='; cat /proc/uptime
  $bb awk '/^(MemAvailable|SwapFree):/ {print}' /proc/meminfo
  # Never wait on a sysfs read holding the shared touch/PMU mutex.
  # If the probe gets stuck, this main loop still records a heartbeat.
  if test -n "$probe" && kill -0 "$probe" 2>/dev/null; then
   echo HARDWARE_PROBE_STILL_RUNNING
  else
   if test -n "$probe"; then
    echo HARDWARE_PROBE_PREVIOUS_SAMPLE
    cat "$probe_file"
   fi
   (
    printf 'PROBE_UPTIME='; cat /proc/uptime
    for file in /sys/firmware/a6_charger_policy/status /sys/firmware/a6_charger_policy/low_battery_status /sys/class/udc/36100000.usb/state /sys/class/net/usb0/operstate /sys/class/net/wlan0/operstate; do
     printf 'READ_BEGIN %s\n' "$file"
     $bb timeout -k 1 3 $bb cat "$file"
     printf 'READ_END rc=%s\n' "$?"
    done
   ) >"$probe_file" 2>&1 &
   probe=$!
  fi
  echo SAMPLE_END
 } >>"$log" 2>&1
 sample=$((sample+1))
 $bb sleep 30
done

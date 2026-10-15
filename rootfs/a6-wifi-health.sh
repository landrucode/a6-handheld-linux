#!/bin/sh
# Autonomous RAM-only monitor. Three failed gateway checks, then bounded backoff.
set -u
umask 077
bb=/bin/busybox
state=/tmp/a6-connection
usr=/tmp/a6-native/tools/usr
. /etc/a6-wifi-common.sh
pidfile=/tmp/a6-wifi-health.pid
if test "${1:-start}" = start; then
 if test -s "$pidfile"; then
  read old <"$pidfile"
  case "$old" in ''|*[!0-9]*) exit 1;; esac
  if test -r /proc/$old/cmdline && $bb tr '\000' ' ' </proc/$old/cmdline | $bb grep -q 'sh /tmp/a6-wifi-health.sh worker'; then exit 0; fi
 fi
 $bb setsid $bb sh /tmp/a6-wifi-health.sh worker </dev/null >/tmp/a6-wifi-health-start.private.log 2>&1 &
 echo $! >"$pidfile"
 exit 0
fi
test "${1:-}" = worker || exit 1
log=/tmp/a6-wifi-health.private.log
failures=0
backoff=60
while :; do
 if test -f /tmp/a6-wifi-health.disabled; then $bb sleep 30; continue; fi
 # An absent AP is left to WPA/DHCP retry; do not repeatedly reset the bus.
 status=$(run wpa_cli -p"$state.ctrl" -iwlan0 status 2>/dev/null)
 if ! printf '%s\n' "$status" | $bb grep -qx 'wpa_state=COMPLETED' || test ! -s "$state.gateway"; then
  failures=0; $bb sleep 30; continue
 fi
 read gateway <"$state.gateway"
 if $bb timeout 3 $bb ping -I wlan0 -c 1 -W 1 "$gateway" >/dev/null 2>&1; then
  failures=0; backoff=60
  printf 'HEALTH_PASS uptime=' >>"$log"; cat /proc/uptime >>"$log"
 else
  failures=$((failures+1))
  printf 'GATEWAY_FAILURE count=%s uptime=' "$failures" >>"$log"; cat /proc/uptime >>"$log"
 fi
 # Optional next-candidate transport diagnostics; no identifiers or packet data.
 for counters in /sys/bus/usb/devices/*:*/a6_transport; do
  test -r "$counters" || continue
  printf 'TRANSPORT uptime=' >>"$log"; cat /proc/uptime >>"$log"
  cat "$counters" >>"$log" 2>/dev/null || :
 done
 if test "$failures" -ge 3; then
  # A responsive neighbour with ICMP filtered is not a reason to reset HSIC.
  if $bb ip neigh show dev wlan0 | $bb grep -F "$gateway " | $bb grep -Eq 'FAILED|INCOMPLETE'; then
   if $bb timeout -k 2 90 $bb sh /tmp/a6-wifi-recover.sh; then
    echo RECOVERY_PASS >>"$log"; backoff=60
   else
    echo RECOVERY_FAILED >>"$log"
   fi
   failures=0
   $bb sleep "$backoff"
   case "$backoff" in 60) backoff=300;; 300) backoff=900;; *) backoff=3600;; esac
  fi
 fi
 if test -f "$log" && test "$( $bb stat -c %s "$log" )" -ge 262144; then $bb mv "$log" "$log.previous"; fi
 $bb sleep 30
done

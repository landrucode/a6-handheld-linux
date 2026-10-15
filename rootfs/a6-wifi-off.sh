#!/bin/sh
set -eu
umask 077
bb=/bin/busybox
state=/tmp/a6-connection
usr=/tmp/a6-native/tools/usr
. /etc/a6-wifi-common.sh
$bb touch /tmp/a6-wifi-health.disabled
if test -s /tmp/a6-wifi-health.pid; then
 read pid </tmp/a6-wifi-health.pid
 case "$pid" in ''|*[!0-9]*) exit 1;; esac
 if test -r /proc/$pid/cmdline && $bb tr '\000' ' ' </proc/$pid/cmdline | $bb grep -q 'sh /tmp/a6-wifi-health.sh worker'; then
  kill -TERM -"$pid" 2>/dev/null || :
 fi
fi
radio_off
test "$(cat /sys/module/brcmfmac/parameters/a6_allow_data_tx)" = N
test "$(get country 12)" = "$(cat "$state.country.original")"
test "$(get mpc 4)" = "$(cat "$state.mpc.original")"
$bb rm -f "$state.connected"
printf 'A6_WIFI_OFF_RESTORED\n'

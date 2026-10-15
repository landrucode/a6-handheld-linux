#!/bin/sh
# Attended diagnostic: data-only TLS uploads; no inbound phone listener.
set -u
umask 077
bb=/bin/busybox
root=/tmp/graphics-runtime
prefix=$root/tmp/a6-log-uplink
read url <"$prefix.url"
trap 'rm -f "$prefix.header" "$prefix.url" "$prefix.pem" "$prefix.body"; exit 0' HUP INT TERM EXIT
samples=${1:-120}
case "$samples" in ''|*[!0-9]*) exit 1;; esac
test "$samples" -ge 1 && test "$samples" -le 960 || exit 1
n=0
while test "$n" -lt "$samples"; do
 {
  echo A6_WIFI_LOG_UPLINK_V1
  cat /proc/uptime
  $bb tail -n 80 /tmp/a6-power-longrun.log
  $bb tail -n 20 /tmp/a6-wifi-health.private.log
  $bb tail -c 4096 /tmp/a6-overnight-workload.private.log | $bb tr '\r' '\n' | $bb tail -n 12
  $bb tail -n 4 "$root/tmp/a6-video-measure.private.log"
 } >"$prefix.body"
 $bb chroot "$root" /usr/bin/curl --silent --show-error --fail --max-time 5 \
  --cacert /tmp/a6-log-uplink.pem --header @/tmp/a6-log-uplink.header \
  --data-binary @/tmp/a6-log-uplink.body --output /dev/null "$url"
 printf 'UPLOAD_RC=%s sample=%s\n' "$?" "$n"
 n=$((n+1))
 $bb sleep 30
done

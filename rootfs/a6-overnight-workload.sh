#!/bin/sh
# One-hour attended regression workload: idle gaps, normal desktop apps, muted local video.
set -u
umask 077
bb=/bin/busybox
root=/tmp/graphics-runtime
user() {
 $bb chroot "$root" /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups \
 /usr/bin/env HOME=/home/a6 USER=a6 XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 "$@"
}
log=/tmp/a6-overnight-workload.private.log
echo $$ >/tmp/a6-overnight-workload.pid
read start rest </proc/uptime
start=${start%%.*}
n=0
while test "$n" -lt 4; do
 {
  printf 'WORKLOAD_CYCLE=%s uptime=' "$n"; cat /proc/uptime
  user /usr/bin/wlopm --on '*'
  if test -p "$root/run/a6-app-control"; then printf 'browser\n' >"$root/run/a6-app-control"; fi
  $bb timeout -k 2 190 $bb chroot "$root" /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups \
   /usr/bin/env HOME=/home/a6 XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 /usr/local/bin/a6-focus-app.sh epiphany
  echo BROWSER_FOCUS_RC=$?
  user /usr/bin/curl --fail --silent --show-error --max-time 20 -I https://example.com >/dev/null
  echo HTTPS_RC=$?
  user /usr/bin/env LD_LIBRARY_PATH=/opt/a6/media-runtime/usr/lib \
   /opt/a6/media-runtime/usr/bin/mpv --no-config --really-quiet --hwdec=no --vo=wlshm --no-audio --length=30 \
   --video-unscaled=yes --fullscreen --vd-lavc-threads=2 --script=/usr/local/share/a6/video-measure.lua /usr/local/share/a6/video-360p.mp4
  echo VIDEO_RC=$?
  user /usr/local/bin/a6-focus-app.sh foot
  echo TERMINAL_FOCUS_RC=$?
  user /usr/bin/wlopm --off '*'
  echo WORKLOAD_IDLE
 } >>"$log" 2>&1
 n=$((n+1))
 read now rest </proc/uptime
 remaining=$((start+n*900-${now%%.*}))
 if test "$remaining" -gt 0; then $bb sleep "$remaining"; fi
done
echo WORKLOAD_COMPLETE >>"$log"

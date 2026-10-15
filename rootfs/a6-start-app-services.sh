#!/bin/sh
# Root-owned, RAM-only cgroup policy and fixed browser-start request queue.
set -eu
bb=/bin/busybox
root=/tmp/graphics-runtime
groups=/tmp/a6-cgroup
if test "${1:-start}" != worker && test -r /tmp/a6-app-services.pid; then
 read -r pid </tmp/a6-app-services.pid
 case "$pid" in ''|*[!0-9]*) exit 1;; esac
 if test -r /proc/$pid/cmdline && $bb tr '\000' ' ' </proc/$pid/cmdline | $bb grep -q 'sh /tmp/a6-start-app-services.sh worker'; then exit 0; fi
fi
if test "${1:-start}" != worker; then
 $bb setsid $bb sh /tmp/a6-start-app-services.sh worker </dev/null >/tmp/a6-app-services.private.log 2>&1 &
 echo $! >/tmp/a6-app-services.pid
 exit 0
fi
umask 077
$bb mkdir -p "$groups" "$root/run/a6-cgroup"
if ! $bb grep -q " $groups cgroup2 " /proc/mounts; then $bb mount -t cgroup2 none "$groups"; fi
echo +memory >"$groups/cgroup.subtree_control"
if ! $bb grep -q " $root/run/a6-cgroup cgroup2 " /proc/mounts; then $bb mount --bind "$groups" "$root/run/a6-cgroup"; fi
# Only the root worker reads requests. UID1000 can write a fixed verb, not code.
test ! -e "$root/run/a6-app-control" || { test -p "$root/run/a6-app-control"; rm "$root/run/a6-app-control"; }
$bb mkfifo "$root/run/a6-app-control"
$bb chown 0:1000 "$root/run/a6-app-control"
$bb chmod 620 "$root/run/a6-app-control"
: >"$root/tmp/a6-oomd-kills.private.log"
printf "closed\n" >"$root/run/a6-browser-status"
$bb chmod 644 "$root/run/a6-browser-status"
$bb chroot "$root" /usr/local/bin/oomd --check-config /usr/local/share/a6/browser-oomd.json
$bb chroot "$root" /usr/local/bin/oomd --config /usr/local/share/a6/browser-oomd.json \
 --cgroup-fs /run/a6-cgroup --interval 1 --runtime-dir /run/a6-oomd \
 --kmsg-override /tmp/a6-oomd-kills.private.log >"$root/tmp/a6-oomd.private.log" 2>&1 &
oomd=$!
$bb sh /tmp/a6-notify-browser-pressure.sh >/tmp/a6-browser-notify.private.log 2>&1 &
notifier=$!
trap 'exit 0' HUP INT TERM
trap 'kill "$oomd" "$notifier" 2>/dev/null || :; rm -f "$root/run/a6-app-control"' EXIT
# Hold a read/write fd open: writers do not block and EOF cannot spin the loop.
exec 3<>"$root/run/a6-app-control"
while IFS= read -r request <&3; do
 case "$request" in
  browser)
   kill -0 "$oomd" 2>/dev/null || { echo PRESSURE_MANAGER_UNAVAILABLE; continue; }
   if test -r "$groups/browser/cgroup.procs" && test -n "$(cat "$groups/browser/cgroup.procs")"; then continue; fi
   echo starting >"$root/run/a6-browser-status"
   A6_BROWSER_PIN_IMAGES=0 \
    $bb sh /tmp/a6-launch-browser-test.sh || { echo failed >"$root/run/a6-browser-status"; echo BROWSER_START_FAILED; continue; }
   $bb setsid $bb sh /tmp/a6-browser-state-watch.sh </dev/null >/tmp/a6-browser-state.private.log 2>&1 &
   ;;
  *) echo UNKNOWN_APP_REQUEST_REJECTED ;;
 esac
done

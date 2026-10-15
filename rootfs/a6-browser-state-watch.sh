#!/bin/sh
# Browser lifecycle feedback only; no memory policy or kill decisions.
set -eu
bb=/bin/busybox
root=/tmp/graphics-runtime
state="$root/run/a6-browser-status"
group=/tmp/a6-cgroup/browser
if $bb chroot "$root" /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c '/usr/local/bin/a6-focus-app.sh epiphany'; then
 if test -n "$(cat "$group/cgroup.procs")"; then echo ready >"$state"; fi
else
 test "$(cat "$state")" = pressure || echo failed >"$state"
fi
while test -n "$(cat "$group/cgroup.procs")"; do $bb sleep 1; done
test "$(cat "$state")" = pressure || echo closed >"$state"

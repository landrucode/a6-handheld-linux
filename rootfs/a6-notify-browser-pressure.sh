#!/bin/sh
# Bridge upstream oomd's completed kill records to the desktop notification bus.
# This script neither samples pressure nor chooses or kills a process.
set -eu
bb=/bin/busybox
root=/tmp/graphics-runtime
$bb tail -n 0 -F "$root/tmp/a6-oomd-kills.private.log" | while IFS= read -r line; do
 case "$line" in
  *'oomd kill:'*' browser '*'killer:kill_by_memory_size_or_growth'*)
   echo pressure >"$root/run/a6-browser-status"
   $bb chroot "$root" /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c \
    'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus notify-send --app-name="A6 Browser" --urgency=critical "Browser closed to keep the desktop responsive" "Memory pressure was sustained. You can reopen Browser from the panel."' || :
   ;;
 esac
done

#!/bin/sh
# RAM-only native desktop startup after the compressed root is mounted.
set -eu
umask 022
/bin/busybox setsid /bin/busybox sh /tmp/a6-power-longrun.sh </dev/null >/tmp/a6-power-longrun-start.log 2>&1 &
bb=/bin/busybox
root=/tmp/graphics-runtime
compositor=hyprland
if test -f "$root/usr/local/share/a6/compositor"; then compositor=$(cat "$root/usr/local/share/a6/compositor"); fi
case "$compositor" in hyprland|labwc) ;; *) exit 2;; esac
exec >/tmp/a6-desktop-boot.private.log 2>&1
if test "$compositor" = labwc; then test -x "$root/opt/a6/labwc-runtime/usr/bin/labwc"; else test -x "$root/usr/bin/Hyprland"; fi
test ! -S "$root/run/user/1000/wayland-1" || exit 0
$bb grep -q 'auto=1 paused=0 fault=0' /sys/firmware/a6_charger_policy/status
$bb grep -q 'enabled=1 .*triggered=0' /sys/firmware/a6_charger_policy/low_battery_status
# Stop only the optional diagnostic painter; never power-monitor processes.
if test -f /tmp/a6-wifi-heartbeat.pid; then
 pid=$(cat /tmp/a6-wifi-heartbeat.pid)
 if test -r "/proc/$pid/cmdline" && $bb grep -q a6-wifi-heartbeat "/proc/$pid/cmdline"; then
  kill "$pid"
 fi
fi
echo 0 >/sys/firmware/a6_usb_screen/enabled
if ! $bb grep -q 'active=1 result=0' /sys/firmware/a6_touch_native/status; then
 echo enable-spi1 >/sys/firmware/a6_touch_transport/enable_clock
 echo enable-pwm-gate >/sys/firmware/a6_touch_clock/enable_gate
 echo start-native-n42 >/sys/firmware/a6_touch_fw_n42/run
fi
$bb grep -q 'active=1 result=0' /sys/firmware/a6_touch_native/status
for name in dev proc sys; do
 if ! $bb grep -q " $root/$name " /proc/mounts; then
  case "$name" in
   dev) $bb mount --bind /dev "$root/dev";;
   proc) $bb mount -t proc proc "$root/proc";;
   sys) $bb mount -t sysfs -o ro sysfs "$root/sys";;
  esac
 fi
done
$bb mkdir -p "$root/dev/pts"
if ! $bb grep -q " $root/dev/pts " /proc/mounts; then
 $bb mount -t devpts devpts "$root/dev/pts"
fi
$bb sh /tmp/a6-desktop-memory.sh prepare
$bb chroot "$root" /bin/bash /usr/local/bin/a6-start-desktop prepare
$bb chroot "$root" /bin/bash /usr/local/bin/a6-prepare-user-desktop
$bb chroot "$root" /proc/1/root/bin/busybox sh /usr/local/bin/a6-label-native-touch
if test "$compositor" = labwc; then
 $bb sh /tmp/a6-desktop-memory.sh enter $bb chroot "$root" /bin/bash -c 'nohup /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c /usr/local/bin/a6-start-user-labwc </dev/null >/tmp/a6-labwc.private.log 2>&1 &'
else
$bb sh /tmp/a6-desktop-memory.sh enter $bb chroot "$root" /bin/bash -c 'nohup /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c /usr/local/bin/a6-start-user-hyprland </dev/null >/tmp/hyprland-user.log 2>&1 &'
$bb sh /tmp/a6-desktop-memory.sh enter $bb chroot "$root" /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c /usr/local/bin/a6-start-native-keyboard
fi
if test -x "$root/usr/local/bin/a6-audio-session" && test -d /dev/snd; then
 $bb chown 1000:1000 /dev/snd/*
 $bb chmod 600 /dev/snd/*
 $bb sh /tmp/a6-desktop-memory.sh enter $bb chroot "$root" /bin/bash -c 'nohup /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c /usr/local/bin/a6-audio-session start </dev/null >/tmp/a6-audio-session.log 2>&1 &'
fi
if test -x "$root/usr/local/bin/a6-app-panel" && test -f /tmp/a6-start-app-services.sh; then
 $bb sh /tmp/a6-start-app-services.sh
 if test "$compositor" = hyprland; then
  $bb sh /tmp/a6-desktop-memory.sh enter $bb chroot "$root" /bin/bash -c 'nohup /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c /usr/local/bin/a6-start-desktop-panel </dev/null >/tmp/a6-panel.private.log 2>&1 &'
 fi
fi
$bb setsid $bb sh /tmp/a6-desktop-workload-log.sh </dev/null >/dev/null 2>&1 &
echo $! >/tmp/a6-desktop-workload.pid
$bb sh /tmp/a6-release-boot-staging.sh
printf 'A6_NATIVE_DESKTOP_READY\n'

#!/bin/sh
# Install only into the current RAM desktop overlay, after root provisioning.
set -eu
test "$(id -u)" = 0
test "$#" = 2
archive=$1
digest=$2
case "$archive" in /tmp/*) ;; *) exit 2;; esac
test "${#digest}" = 64
case "$digest" in *[!0-9a-f]*) exit 2;; esac
root=/tmp/graphics-runtime
test -x "$root/usr/bin/Hyprland"
test -d /dev/snd
grep -q 'auto=1 paused=0 fault=0' /sys/firmware/a6_charger_policy/status
grep -q 'enabled=1 .*triggered=0' /sys/firmware/a6_charger_policy/low_battery_status
printf '%s  %s\n' "$digest" "$archive" | sha256sum -c -
test ! -e "$root/opt/a6/audio-runtime"
mkdir -p "$root/opt/a6/audio-runtime"
tar -xzf "$archive" -C "$root/opt/a6/audio-runtime" --strip-components=1 runtime
chmod -R a+rX "$root/opt/a6/audio-runtime"
cp "$root/opt/a6/audio-runtime/usr/local/bin/a6-audio-session" "$root/usr/local/bin/a6-audio-session"
chmod 755 "$root/usr/local/bin/a6-audio-session"
# Only the desktop owner can open this candidate's ALSA nodes.
chown 1000:1000 /dev/snd/*
chmod 600 /dev/snd/*
printf 'A6_AUDIO_RUNTIME_INSTALLED\n'

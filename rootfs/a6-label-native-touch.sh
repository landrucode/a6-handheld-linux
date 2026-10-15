#!/bin/sh
# Minimal RAM-root libinput label for the exact N42 native kernel device.
set -eu
umask 022
test "$(id -u)" = 0
mkdir -p /run/udev/data
matrix_file=/usr/local/share/a6/touch-calibration.matrix
test -r "$matrix_file"
matrix=$(cat "$matrix_file")
printf '%s\n' "$matrix" | awk 'NF != 6 { exit 1 } { for (i=1;i<=6;i++) if ($i !~ /^-?[0-9]+([.][0-9]+)?$/) exit 1 }'
found=0
for node in /sys/class/input/event*; do
    test -r "$node/device/name" || continue
    IFS= read -r name < "$node/device/name"
    test "$name" = 'A6 N42 native touchscreen' || continue
    IFS= read -r number < "$node/dev"
    case "$number" in 13:*) minor=${number#13:};; *) exit 1;; esac
    case "$minor" in ''|*[!0-9]*) exit 1;; esac
    device=/dev/input/${node##*/}
    test -c "$device"
    printf 'I:1\nE:ID_INPUT=1\nE:ID_INPUT_TOUCHSCREEN=1\nE:ID_SEAT=seat0\nG:seat\nQ:seat\n' > "/run/udev/data/c$number"
    printf 'E:LIBINPUT_CALIBRATION_MATRIX=%s\n' "$matrix" >> "/run/udev/data/c$number"
    chown 0:1000 "$device"
    chmod 660 "$device"
    found=$((found + 1))
done
test "$found" = 1
echo A6_NATIVE_TOUCH_LABEL_READY

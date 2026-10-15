#!/bin/bash
# Label only our two synthetic devices in this minimal RAM root's udev database.
# No udev daemon is installed; run before Weston's initial enumeration.
set -euo pipefail
mkdir -p /run/udev/data
count=0
for node in /sys/class/input/event*; do
    [[ -f "$node/device/name" ]] || continue
    name=$(cat "$node/device/name")
    case "$name" in
        'A6 USB synthetic keyboard') role=KEYBOARD ;;
        'A6 USB synthetic pointer') role=MOUSE ;;
        *) continue ;;
    esac
    number=$(cat "$node/dev")
    [[ "$number" =~ ^13:[0-9]+$ ]] || exit 1
    {
        printf 'I:1\nE:ID_INPUT=1\nE:ID_INPUT_%s=1\nE:ID_SEAT=seat0\nG:seat\nQ:seat\n' "$role"
        [[ "$role" != KEYBOARD ]] || printf 'E:ID_INPUT_KEY=1\n'
    } > "/run/udev/data/c$number"
    ((count+=1))
done
[[ "$count" == 2 ]]
echo A6_INPUT_LABELS_READY

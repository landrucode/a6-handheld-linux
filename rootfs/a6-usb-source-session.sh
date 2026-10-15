#!/bin/sh
# RAM-only, attended N42 reconnect trial. Start before unplugging USB.
# Uses the PMU's independently sampled VBUS state and the kernel UDC API.
set -eu

udc=${A6_USB_UDC_SOFT_CONNECT:-/sys/class/udc/36100000.usb/soft_connect}
online_path=${A6_USB_ONLINE_PATH:-/sys/class/power_supply/a6-d1972-usb/online}
max_samples=${A6_USB_SESSION_SAMPLES:-600}

case "$max_samples" in
    ''|*[!0-9]*) echo "invalid sample limit" >&2; exit 2 ;;
esac
[ "$max_samples" -ge 1 ] && [ "$max_samples" -le 3600 ] || exit 2
[ -w "$udc" ] && [ -r "$online_path" ] || exit 3

previous=$(cat "$online_path")
[ "$previous" = 1 ] || { echo "USB source not online at start" >&2; exit 4; }
echo "a6-usb-source-session: armed, maximum $max_samples seconds"

sample=0
pending=$previous
stable=0
while [ "$sample" -lt "$max_samples" ]; do
    sleep 1
    sample=$((sample + 1))
    current=$(cat "$online_path") || {
        echo "sample=$sample PMU read failed; retrying" >&2
        continue
    }
    case "$current" in
        0|1) ;;
        *) echo "sample=$sample invalid PMU ONLINE value: $current; retrying" >&2; continue ;;
    esac
    if [ "$current" = "$previous" ]; then
        pending=$previous
        stable=0
        continue
    fi
    if [ "$current" != "$pending" ]; then
        pending=$current
        stable=1
        continue
    fi
    stable=$((stable + 1))
    if [ "$stable" -ge 2 ]; then
        if [ "$current" = 0 ]; then
            echo disconnect > "$udc" || exit 7
            echo "sample=$sample PMU=0 UDC=disconnect"
        else
            echo connect > "$udc" || exit 8
            echo "sample=$sample PMU=1 UDC=connect"
        fi
        previous=$current
        stable=0
    fi
done
echo "a6-usb-source-session: sample limit reached, PMU=$previous"

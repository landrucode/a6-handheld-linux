#!/bin/sh
# Attended RAM-only test: let native reconnect run, then try one delayed UDC cycle.
set -eu

udc=${A6_USB_UDC_SOFT_CONNECT:-/sys/class/udc/36100000.usb/soft_connect}
online=${A6_USB_ONLINE_PATH:-/sys/class/power_supply/a6-d1972-usb/online}
delay=${A6_USB_RECOVERY_DELAY:-120}
limit=${A6_USB_RECOVERY_LIMIT:-600}
interval_us=${A6_USB_RECOVERY_INTERVAL_US:-1000000}
pidfile=${A6_USB_RECOVERY_PIDFILE:-/tmp/a6-usb-delayed-recovery.pid}

case "$delay:$limit:$interval_us" in
    *[!0-9:]*|:*|*::*|*:) exit 2 ;;
esac
[ "$delay" -ge 5 ] && [ "$delay" -le 180 ] || exit 2
[ "$limit" -ge 180 ] && [ "$limit" -le 9000 ] || exit 2
[ "$interval_us" -eq 1000000 ] || [ "$interval_us" -eq 100000 ] || exit 2
[ -w "$udc" ] && [ -r "$online" ] || exit 3
[ "$(cat "$online")" = 1 ] || exit 4
printf '%s\n' "$$" > "$pidfile"

echo "a6-delayed-recovery: armed; native path first; delay=${delay}s interval_us=$interval_us"
phase=online
streak=0
sample=0
while [ "$sample" -lt "$limit" ]; do
    /bin/busybox usleep "$interval_us"
    sample=$((sample + 1))
    value=$(cat "$online") || { echo "PMU read failed at $sample"; exit 5; }
    case "$phase:$value" in
        online:0|offline:1) streak=$((streak + 1)) ;;
        online:1|offline:0) streak=0 ;;
        *) echo "invalid PMU ONLINE=$value at $sample"; exit 6 ;;
    esac
    if [ "$phase" = online ] && [ "$streak" -ge 2 ]; then
        phase=offline
        streak=0
        echo "sample=$sample PMU offline; native UDC left untouched"
    elif [ "$phase" = offline ] && [ "$streak" -ge 2 ]; then
        echo "sample=$sample PMU returned; native USB has ${delay}s before UDC action"
        sleep "$delay"
        [ "$(cat "$online")" = 1 ] || {
            echo "source absent at action time; no UDC write"
            exit 7
        }
        echo disconnect > "$udc"
        echo "PMU=1 UDC=disconnect after native interval"
        sleep 1
        echo connect > "$udc"
        echo "PMU=1 UDC=connect; one-shot complete"
        exit 0
    fi
done
echo "sample limit reached without complete source cycle"
exit 8

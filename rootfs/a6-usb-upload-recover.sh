#!/bin/sh
# Explicit Ethernet-only recovery, before radio/desktop startup.
set -eu
umask 077
test ! -e /tmp/a6-connection.connected
test ! -e /tmp/a6-wifi-boot.ready
test ! -d /sys/class/net/wlan0
# The caller has already stopped its uniquely owned receiver.
listeners=$(busybox netstat -lnt)
if printf '%s\n' "$listeners" | busybox grep -q ':8083 '; then
    exit 1
fi
lock=/tmp/a6-usb-upload-recovery.lock
mkdir "$lock"
trap 'rmdir "$lock"' EXIT
trap 'exit 1' HUP INT TERM
record=/tmp/a6-usb-upload-recovery-$(busybox date +%s)-$$
{
    echo A6_USB_UPLOAD_RECOVERY_V2
    cat /proc/uptime
    for name in carrier operstate statistics/rx_packets statistics/tx_packets statistics/rx_errors statistics/tx_errors; do
        printf '%s=' "$name"
        cat "/sys/class/net/usb0/$name"
    done
} > "$record.before"
busybox ip link set usb0 down
busybox ip link set usb0 up
busybox ip link show usb0 > "$record.after"
printf '%s\n' A6_USB_UPLOAD_RECOVERY_DONE

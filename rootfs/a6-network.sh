#!/bin/sh
# Only RAM and the USB point-to-point link. Serial starts even on failure.
exec > /tmp/a6-network.log 2>&1
set -eu
/bin/busybox ip link set lo up
/bin/busybox ip address replace 127.0.0.1/8 dev lo
/bin/busybox ip address replace 192.168.7.2/30 dev usb0
/bin/busybox ip link set usb0 up
/bin/busybox httpd -p 192.168.7.2:8080 -h /www
printf 'A6 NETWORK READY 192.168.7.2:8080\n'
# Default Wi-Fi startup waits for the private RAM provisioning marker.
if test -f /etc/a6-wifi-boot.sh; then
 /bin/busybox setsid /bin/busybox sh /etc/a6-wifi-boot.sh </dev/null >/dev/null 2>&1 &
fi

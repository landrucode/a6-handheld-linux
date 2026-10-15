#!/bin/sh
set -eu
case "$1" in
 deconfig) busybox ip address flush dev wlan0
  busybox rm -f /tmp/a6-connection.address /tmp/a6-connection.gateway /tmp/a6-connection.connected;;
 bound|renew)
  busybox ifconfig wlan0 "$ip" netmask "$subnet"
  gateway=${router%% *}
  test -z "$gateway" || busybox ip route replace default via "$gateway" dev wlan0
  : >/etc/resolv.conf
  for resolver in $dns; do printf 'nameserver %s\n' "$resolver" >>/etc/resolv.conf; done
  # DNS configuration is public; unprivileged clients must be able to read it.
  busybox chmod 644 /etc/resolv.conf
  if test -d /tmp/graphics-runtime/etc; then
   busybox cp /etc/resolv.conf /tmp/graphics-runtime/etc/resolv.conf.new
   busybox chmod 644 /tmp/graphics-runtime/etc/resolv.conf.new
   busybox mv /tmp/graphics-runtime/etc/resolv.conf.new /tmp/graphics-runtime/etc/resolv.conf
  fi
  printf '%s\n' "$ip" >/tmp/a6-connection.address
  printf '%s\n' "$gateway" >/tmp/a6-connection.gateway
  busybox touch /tmp/a6-connection.connected
  printf '%s %s %s\n' "$1" "${lease:-0}" "$(busybox date +%s)" >>/tmp/a6-connection.lease.events
  ;;
esac

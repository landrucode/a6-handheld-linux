#!/bin/sh
# Default RAM-only startup after private USB provisioning; no host trial loop.
set -eu
umask 077
exec >/tmp/a6-wifi-boot.private.log 2>&1
bb=/bin/busybox
state=/tmp/a6-connection
usr=/tmp/a6-native/tools/usr
. /etc/a6-wifi-common.sh
trap 'radio_off; exit 1' HUP INT TERM
success=0
trap 'test "$success" = 1 || radio_off' EXIT
# An atomic ready marker is written only after uploads and clock/secret injection.
while test ! -f /tmp/a6-wifi-boot.ready; do $bb sleep 1; done
$bb rm /tmp/a6-wifi-boot.ready
# Trusted initial transport is the USB peer. No credentials are in these hashes.
(cd /; $bb sha256sum -c /tmp/a6-boot.sha256)
epoch=$(cat /tmp/a6-boot.epoch)
case "$epoch" in ''|*[!0-9]*) exit 1;; esac
test "$epoch" -ge 1780000000 && test "$epoch" -le 4102444800
$bb date -s "@$epoch" >/dev/null
$bb mkdir -p /tmp/a6-native /lib/firmware
$bb tar -xzf /tmp/a6-native.tar.gz -C /tmp/a6-native
if test ! -f /tmp/a6-network-bootstrap; then
 $bb sh /etc/a6-verify-update.sh /tmp/a6-update.candidate
fi
# Install default DROP before any WLAN bring-up or data TX.
for name in $(cat /tmp/a6-firewall.modules); do load "$name"; done
run nft -f /etc/a6-wifi.nft
test ! -e /proc/net/if_inet6
# Mount the normal compressed base without expanding its files into RAM.
if test ! -f /tmp/a6-network-bootstrap && ! $bb grep -q ' /tmp/graphics-runtime overlay ' /proc/mounts; then
 $bb sh /etc/a6-mount-compressed-desktop.sh native
fi
if test -b /dev/zram0 && ! $bb grep -q '^/dev/zram0 ' /proc/swaps; then
 echo 134217728 >/sys/block/zram0/disksize
 $bb mkswap /dev/zram0 >/dev/null
 $bb swapon /dev/zram0
fi
$bb cp /tmp/a6-native/tools/usr/lib/firmware/regulatory.db* /lib/firmware/
for name in sha256 af_packet cfg80211 brcmutil brcmfmac brcmfmac-wcc; do load "$name"; done
test "$(cat /sys/module/brcmfmac/parameters/a6_allow_data_tx)" = N
test "$(cat /sys/module/brcmfmac/parameters/a6_tx_hsic_header)" = N
$bb grep -q 'auto=1 paused=0 fault=0' /sys/firmware/a6_charger_policy/status
$bb grep -q 'enabled=1 .*triggered=0' /sys/firmware/a6_charger_policy/low_battery_status
attempt=0
while test ! -d /sys/class/net/wlan0; do
 attempt=$((attempt+1))
 if echo start-native-n42-wlan >/sys/firmware/a6_wifi_ehci_enum/run; then
  test -d /sys/class/net/wlan0
  break
 fi
 # Retry only after the failed attempt has fully restored hardware ownership.
 $bb grep -q 'active=0 .*restore=0' /sys/firmware/a6_wifi_ehci_enum/native
 test "$attempt" -lt 3
 printf 'A6_WIFI_BOOT_NATIVE_RETRY %s\n' "$attempt"
 $bb sleep 2
done
get country 12 >"$state.country.original"
get mpc 4 >"$state.mpc.original"
run iw dev wlan0 vendor recv 0x001018 0x1 /etc/a6-boot/country-gb.ioctl >/dev/null
country=$(get country 12)
case "$country" in 47420000????????47420000) ;; *) exit 1;; esac
run iw dev wlan0 vendor recv 0x001018 0x1 /etc/a6-boot/mpc-off.ioctl >/dev/null
test "$(get mpc 4)" = 00000000
# Refuse broad or Wi-Fi listeners, apart from the DHCP client's port68.
run ss -H -ltnup >"$state.sockets"
$bb awk '
 $1=="tcp" || $1=="udp" {
  if($1=="udp" && $5 ~ /:68$/)next
  if($5 !~ /^(127\.0\.0\.1|192\.168\.7\.2):/)exit 1
 }' "$state.sockets"
test "$($bb stat -c %a /tmp/a6-wifi-boot.conf)" = 600
$bb mv /tmp/a6-wifi-boot.conf "$state.conf"
mac=$(cat /tmp/a6-boot.mac)
case "$mac" in ??:??:??:??:??:??) ;; *) exit 1;; esac
$bb ip link set wlan0 address "$mac"
echo Y >/sys/module/brcmfmac/parameters/a6_allow_data_tx
$bb ip link set wlan0 up
# Main delivery path: disable station power saving before association.
run iw dev wlan0 set power_save off
run iw dev wlan0 get power_save >"$state.power-save"
$bb grep -qx "Power save: off" "$state.power-save"
$bb cp "$state.conf" /tmp/a6-wifi-recovery.conf
$bb chmod 600 /tmp/a6-wifi-recovery.conf
run wpa_supplicant -B -Dnl80211 -iwlan0 -c"$state.conf" -C"$state.ctrl" -P"$state.wpa.pid" >/dev/null 2>&1
$bb rm "$state.conf"
# Normal service behaviour: AP/DHCP absence is retried without the laptop.
$bb setsid $bb udhcpc -f -i wlan0 -t 3 -T 3 -A 5 -p "$state.dhcp.pid" -s /etc/a6-wifi-dhcp.sh </dev/null >"$state.dhcp.log" 2>&1 &
$bb sleep 1
test -s "$state.dhcp.pid"
kill -0 "$(cat "$state.dhcp.pid")"
success=1
$bb rm -f /tmp/a6-wifi-health.disabled
$bb sh /tmp/a6-wifi-health.sh start
# Desktop setup runs independently of AP/DHCP availability.
if test ! -f /tmp/a6-network-bootstrap; then
 $bb setsid $bb sh /etc/a6-start-native-desktop.sh </dev/null >/tmp/a6-desktop-launch.log 2>&1 &
fi
n=0
while test ! -s "$state.address" && test "$n" -lt 45; do n=$((n+1)); $bb sleep 1; done
if test -s "$state.address"; then
 printf 'A6_WIFI_BOOT_CONNECTED\n'
else
 printf 'A6_WIFI_BOOT_WAITING_FOR_LINK; DHCP and WPA keep retrying\n'
fi

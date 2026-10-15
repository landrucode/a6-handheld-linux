#!/bin/sh
# Root-only RAM recovery; no reboot, USB rebinding, or battery-policy changes.
set -eu
umask 077
bb=/bin/busybox
state=/tmp/a6-connection
usr=/tmp/a6-native/tools/usr
config=/tmp/a6-wifi-recovery.conf
. /etc/a6-wifi-common.sh
lock=/tmp/a6-wifi-recovery.lock
mkdir "$lock" || exit 1
success=0
trap 'test "$success" = 1 || radio_off; rmdir "$lock"' EXIT
trap 'exit 1' HUP INT TERM
record=/tmp/a6-wifi-recovery.private.log
test ! -f "$record" || $bb mv "$record" "$record.previous"
exec >"$record" 2>&1
echo RECOVERY_BEFORE
cat /proc/uptime
cat /sys/firmware/a6_charger_policy/status /sys/firmware/a6_charger_policy/low_battery_status
$bb grep -q 'auto=1 paused=0 fault=0' /sys/firmware/a6_charger_policy/status
$bb grep -q 'enabled=1 .*triggered=0' /sys/firmware/a6_charger_policy/low_battery_status
test "$( $bb stat -c %a "$config" )" = 600
test "$( $bb stat -c %u "$config" )" = 0
run wpa_cli -p"$state.ctrl" -iwlan0 status || :
run iw dev wlan0 station dump || :
$bb ip neigh show dev wlan0 || :
for field in rx_packets tx_packets rx_errors tx_errors rx_dropped tx_dropped; do
 printf '%s=' "$field"; cat /sys/class/net/wlan0/statistics/$field || :
done
$bb dmesg | $bb tail -n 60
for counters in /sys/bus/usb/devices/*:*/a6_transport; do
 test -r "$counters" || continue
 cat "$counters" || :
done
# Preserve pre-recovery evidence, then release and re-create native HSIC ownership.
echo RECOVERY_NATIVE_STOP
radio_off
$bb rm -f "$state.address" "$state.gateway" "$state.connected"
echo stop-native-n42-wlan >/sys/firmware/a6_wifi_ehci_enum/run
echo RECOVERY_NATIVE_START
echo start-native-n42-wlan >/sys/firmware/a6_wifi_ehci_enum/run
test -d /sys/class/net/wlan0
run nft list chain ip a6_guard input | $bb grep -q 'policy drop'
get country 12 >"$state.country.original"
get mpc 4 >"$state.mpc.original"
run iw dev wlan0 vendor recv 0x001018 0x1 /etc/a6-boot/country-gb.ioctl >/dev/null
country=$(get country 12)
case "$country" in 47420000????????47420000) ;; *) exit 1;; esac
run iw dev wlan0 vendor recv 0x001018 0x1 /etc/a6-boot/mpc-off.ioctl >/dev/null
test "$(get mpc 4)" = 00000000
mac=$(cat /tmp/a6-boot.mac)
case "$mac" in ??:??:??:??:??:??) ;; *) exit 1;; esac
$bb ip link set wlan0 address "$mac"
echo Y >/sys/module/brcmfmac/parameters/a6_allow_data_tx
$bb ip link set wlan0 up
run iw dev wlan0 set power_save off
run iw dev wlan0 get power_save | $bb grep -qx 'Power save: off'
run wpa_supplicant -B -Dnl80211 -iwlan0 -c"$config" -C"$state.ctrl" -P"$state.wpa.pid" >/dev/null 2>&1
$bb setsid $bb udhcpc -f -i wlan0 -t 3 -T 3 -A 5 -p "$state.dhcp.pid" -s /etc/a6-wifi-dhcp.sh </dev/null >"$state.dhcp.log" 2>&1 &
n=0
while test "$n" -lt 20; do
 if test -s "$state.gateway"; then
  read gateway <"$state.gateway"
  if $bb timeout 3 $bb ping -I wlan0 -c 1 -W 1 "$gateway" >/dev/null 2>&1; then
   echo RECOVERY_GATEWAY_PASS
   $bb touch "$state.connected"
   success=1
   exit 0
  fi
 fi
 n=$((n+1)); $bb sleep 2
done
echo RECOVERY_GATEWAY_NOT_RESTORED
exit 1

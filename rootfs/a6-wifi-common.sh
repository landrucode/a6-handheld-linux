# Shared RAM-only country/MPC restoration helpers.
run() { "$usr/lib/ld-linux-armhf.so.3" --library-path "$usr/lib" "$usr/bin/$@"; }
load() { test -d "/sys/module/$(printf '%s' "$1" | $bb tr - _)" || $bb insmod "/tmp/a6-native/modules/$1.ko"; }
get() {
 run iw dev wlan0 vendor recv 0x001018 0x1 "/etc/a6-boot/$1-get.ioctl" >"$state.$1.reply"
 $bb awk -v expected="$2" -f /etc/a6-vendor-data.awk "$state.$1.reply"
}
set_hex() {
 { $bb xxd -p "/etc/a6-boot/$1-set.prefix"; printf '%s\n' "$2"; } | $bb xxd -r -p >"$state.set.ioctl"
 run iw dev wlan0 vendor recv 0x001018 0x1 "$state.set.ioctl" >/dev/null
}
radio_off() {
 for kind in dhcp wpa; do
  test ! -f "$state.$kind.pid" || kill "$(cat "$state.$kind.pid")" 2>/dev/null || true
 done
 $bb ip link set wlan0 down 2>/dev/null || true
 test ! -w /sys/module/brcmfmac/parameters/a6_allow_data_tx || echo N >/sys/module/brcmfmac/parameters/a6_allow_data_tx
 $bb rm -f "$state.conf" /tmp/a6-wifi-boot.conf
 if test -f "$state.country.original"; then set_hex country "$(cat "$state.country.original")" || true; fi
 if test -f "$state.mpc.original"; then set_hex mpc "$(cat "$state.mpc.original")" || true; fi
}

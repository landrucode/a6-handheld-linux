#!/bin/sh
# Start a RAM-only authenticated time client; never bring up or reset a radio.
set -eu
umask 077
bb=/bin/busybox
prefix=/tmp/a6-time-runtime
runtime=$prefix/runtime
state=/tmp/a6-time
test -x "$runtime/usr/bin/chronyd"
test -f "$prefix/ca-bundle.pem"
test ! -e "$state/chronyd.pid"
# Provisioning already supplies a TLS-valid initial clock. Wait for DHCP only.
n=0
while test ! -s /tmp/a6-connection.address; do
 n=$((n+1)); test "$n" -le 120; $bb sleep 1
done
$bb mkdir -p "$state"
test -e /etc/passwd || printf 'root:*:0:0:root:/root:/bin/sh\n' >/etc/passwd
test -e /etc/group || printf 'root:*:0:\n' >/etc/group
if ! $bb grep -q '^a6-time:\*:123:123:' /etc/passwd; then
 ! $bb grep -q '^a6-time:' /etc/passwd
 ! $bb awk -F: '$3==123 {found=1} END {exit !found}' /etc/passwd
 printf 'a6-time:*:123:123:NTS:/tmp/a6-time:/bin/false\n' >>/etc/passwd
fi
if ! $bb grep -q '^a6-time:\*:123:' /etc/group; then
 ! $bb grep -q '^a6-time:' /etc/group
 ! $bb awk -F: '$3==123 {found=1} END {exit !found}' /etc/group
 printf 'a6-time:*:123:\n' >>/etc/group
fi
$bb cp "$runtime/config/chrony.conf" "$prefix/chrony.conf"
$bb chmod 755 "$prefix" "$runtime"
$bb chmod 444 "$prefix/chrony.conf" "$prefix/ca-bundle.pem"
$bb chmod 700 "$state"
$bb chown -R 123:123 "$state"
# Resolver addresses are public; credentials remain separate and owner-only.
$bb chmod 644 /etc/resolv.conf
lib=$runtime/usr/lib
if test -f "$lib/a6-chrony-time64.so"; then
 export LD_PRELOAD="$lib/a6-chrony-time64.so"
fi
exec "$lib/ld-linux-armhf.so.3" --library-path "$lib" "$runtime/usr/bin/chronyd" \
 -4 -d -u a6-time -F 1 -f "$prefix/chrony.conf"

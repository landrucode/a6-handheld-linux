#!/bin/sh
# Discard redundant RAM upload containers after the desktop is ready.
# Extracted modules, compressed mounted roots and signed metadata stay intact.
set -eu
bb=/bin/busybox
test -f /tmp/a6-boot.sha256
total=0
for file in /tmp/a6-native.tar.gz /tmp/a6-update.candidate/a6-wifi.img3; do
 test -f "$file" || continue
 relative=${file#/}
 expected=$($bb awk -v path="$relative" '$2==path {print $1}' /tmp/a6-boot.sha256)
 test "${#expected}" = 64
 printf '%s  %s\n' "$expected" "$file" | $bb sha256sum -c - >/dev/null
 bytes=$($bb stat -c %s "$file")
 $bb rm "$file"
 total=$((total+bytes))
done
printf 'A6_BOOT_STAGING_RELEASED bytes=%s\n' "$total"

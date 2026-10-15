#!/bin/sh
# Verification only: never executes or installs an image, and preserves fallback.
set -eu
umask 077
test "$#" = 1
test "$1" = /tmp/a6-update.candidate
cd "$1"
usr=/tmp/a6-native/tools/usr
"$usr/lib/ld-linux-armhf.so.3" --library-path "$usr/lib" "$usr/bin/openssl" \
 pkeyutl -verify -rawin -pubin -inkey /etc/a6-update-public.pem \
 -in manifest.sha256 -sigfile manifest.sig >/dev/null 2>&1
# Signed manifests have two fixed filenames; paths and extra entries are rejected.
/bin/busybox awk '
 NR==1 { if($0 !~ /^[0-9a-f]+  a6-wifi.img3$/ || length($1)!=64)exit 1 }
 NR==2 { if($0 !~ /^[0-9a-f]+  a6-desktop.squashfs$/ || length($1)!=64)exit 1 }
 NR>2 {exit 1}
 END {if(NR!=2)exit 1}' manifest.sha256
/bin/busybox sha256sum -c manifest.sha256 >/dev/null
printf 'A6_SIGNED_UPDATE_VERIFIED\n'

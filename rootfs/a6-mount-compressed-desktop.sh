#!/bin/sh
# RAM-only desktop base and writable overlay; never mounts internal storage.
set -eu
image=/tmp/a6-desktop.squashfs
base=/tmp/a6-desktop-base
state=/tmp/a6-desktop-overlay
target=/tmp/graphics-runtime
expected=7520a8990582ae06c1c42c4338796d218b816e95538a18e0ce94b15cb1091864
case "${1:-baseline}" in
    baseline) ;;
    native)
        expected=88d9362f58826f5154d2548edfe86c44b63e7f121ebc3804eb50402a85cf394e
        if test -r /etc/a6-boot/desktop.sha256; then expected=$(cat /etc/a6-boot/desktop.sha256); fi
        ;;
    *) echo 'Unknown RAM desktop profile' >&2; exit 1 ;;
esac
test "$#" -le 1
test "$(busybox id -u)" = 0
test -f "$image"
test ! -e "$base"
test ! -e "$state"
test ! -e "$target"
printf '%s  %s\n' "$expected" "$image" | busybox sha256sum -c -
busybox grep -q squashfs /proc/filesystems
busybox grep -q overlay /proc/filesystems
mkdir "$base" "$state" "$target"
success=0
cleanup() {
    if test "$success" = 0; then
        busybox umount "$target" 2>/dev/null || true
        busybox umount "$base" 2>/dev/null || true
        busybox umount "$state" 2>/dev/null || true
        busybox rmdir "$target" "$base" "$state" 2>/dev/null || true
    fi
}
trap cleanup EXIT
busybox mount -t squashfs -o loop,ro "$image" "$base"
busybox mount -t tmpfs -o size=192m,mode=0700,nosuid,nodev tmpfs "$state"
mkdir "$state/upper" "$state/work"
busybox mount -t overlay overlay \
    -o "lowerdir=$base/graphics-runtime,upperdir=$state/upper,workdir=$state/work" "$target"
busybox chmod 0755 "$target"
# Desktop helpers come from the verified image. Retained kernel helpers must
# not replace its theme or configuration after mounting.
compositor=hyprland
if test -r "$target/usr/local/share/a6/compositor"; then compositor=$(cat "$target/usr/local/share/a6/compositor"); fi
case "$compositor" in
 labwc) test -x "$target/opt/a6/labwc-runtime/usr/bin/labwc"; test -x "$target/usr/local/bin/a6-start-user-labwc";;
 hyprland) test -x "$target/usr/bin/Hyprland"; test -x "$target/usr/local/bin/a6-start-user-hyprland";;
 *) exit 2;;
esac
success=1
echo A6_COMPRESSED_DESKTOP_MOUNTED
grep MemAvailable /proc/meminfo

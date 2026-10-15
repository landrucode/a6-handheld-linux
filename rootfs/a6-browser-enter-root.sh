#!/bin/sh
# WebKit launch in a private root; never changes the live desktop /usr.
set -eu
bb=/bin/busybox
root=/tmp/graphics-runtime
state=/tmp/a6-browser-overlay
$bb mount --make-rprivate /
$bb mkdir -p "$state"
$bb mount -t tmpfs -o size=16m,mode=0700,nosuid,nodev tmpfs "$state"
$bb mkdir "$state/base" "$state/upper" "$state/work"
$bb chmod 0755 "$state/upper"
$bb mount --bind "$root/usr" "$state/base"
$bb mount -t overlay overlay -o "lowerdir=/tmp/graphics-runtime/opt/a6/browser-runtime/usr:$state/base,upperdir=$state/upper,workdir=$state/work" "$root/usr"
cd "$root"
$bb mkdir -p .browser-old-root
$bb pivot_root . .browser-old-root
cd /
bb=/usr/local/lib/a6-browser/busybox
$bb umount -l /.browser-old-root
$bb rmdir /.browser-old-root
exec /usr/bin/setpriv --nnp --reuid=1000 --regid=1000 --clear-groups /usr/bin/env HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash /bin/bash -c '
 set -eu
 export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
 export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
 export GSK_RENDERER=cairo
 export WEBKIT_SKIA_ENABLE_CPU_RENDERING=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
 export LC_ALL=C.UTF-8
 export GSETTINGS_SCHEMA_DIR=/usr/share/glib-2.0/schemas
 export PATH=/usr/bin:/bin
 unset LD_LIBRARY_PATH LD_PRELOAD WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS WEBKIT_DISABLE_SANDBOX
 exec /usr/bin/epiphany --profile=/home/a6/browser https://example.com
'

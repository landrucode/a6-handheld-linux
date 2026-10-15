#!/bin/bash
# Our handheld desktop with Pixman rendering, UID1000 and RAM only.
set -euo pipefail
[[ $(id -u) == 1000 && $(id -g) == 1000 ]]
export XDG_RUNTIME_DIR=/run/user/1000
unset WAYLAND_DISPLAY DISPLAY
export LIBSEAT_BACKEND=seatd WLR_RENDERER=pixman
export WLR_BACKENDS=drm,libinput WLR_DRM_DEVICES=/dev/dri/card0
export LD_LIBRARY_PATH=/opt/a6/labwc-runtime/usr/lib
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export PATH=/usr/local/bin:/usr/bin:/bin
ulimit -c 0
exec /opt/a6/labwc-runtime/usr/bin/labwc --config-dir /usr/local/share/a6/labwc

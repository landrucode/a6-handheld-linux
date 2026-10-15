#!/bin/bash
# Run as the a6 user after privileged seat/input setup. Never setuid this file.
set -euo pipefail
[[ $(id -u) == 1000 && $(id -g) == 1000 ]]
[[ -S /run/seatd.sock && -w /run/seatd.sock ]]
export XDG_RUNTIME_DIR=/run/user/1000
[[ -d "$XDG_RUNTIME_DIR" && -O "$XDG_RUNTIME_DIR" ]]
[[ $(stat -c %a "$XDG_RUNTIME_DIR") == 700 ]]
[[ ! -e "$XDG_RUNTIME_DIR/wayland-1" ]]
cd /home/a6
ulimit -c 0
ulimit -v 524288
# One raster worker lets the compositor avoid doing every llvmpipe job inline.
# Keep this bounded on the dual-core phone; measure gestures on hardware.
exec env -i HOME=/home/a6 USER=a6 LOGNAME=a6 SHELL=/bin/bash \
 PATH=/usr/local/bin:/usr/bin:/bin LC_ALL=C.UTF-8 \
 XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" LIBSEAT_BACKEND=seatd \
 LD_LIBRARY_PATH=/opt/a6/aquamarine-simpledrm AQ_DRM_DEVICES=/dev/dri/card0 \
 LIBGL_ALWAYS_SOFTWARE=true GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=1 \
 HYPRLAND_NO_CRASHREPORTER=1 Hyprland --config /usr/local/share/a6/hyprland.lua

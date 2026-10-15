#!/bin/bash
# UID1000 desktop panel and notification service, sharing a private user bus.
set -euo pipefail
[[ $(id -u) == 1000 ]]
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
if [[ -L "$XDG_RUNTIME_DIR/wayland-1" ]]; then
    panel=/usr/local/bin/a6-labwc-panel
else
    panel=/usr/local/bin/a6-app-panel
for instance in "$XDG_RUNTIME_DIR"/hypr/*; do
 [[ -S "$instance/.socket.sock" ]] || continue
 export HYPRLAND_INSTANCE_SIGNATURE=${instance##*/}
 break
done
[[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]
fi
if [[ ! -S "$XDG_RUNTIME_DIR/bus" ]]; then
 prefix=/opt/a6/audio-runtime/usr
 LD_LIBRARY_PATH="$prefix/lib" "$prefix/bin/dbus-daemon" \
  --config-file="$prefix/share/dbus-1/session.conf" \
  --address="$DBUS_SESSION_BUS_ADDRESS" --fork
fi
set -a
source /usr/local/share/a6/theme/palette.sh
set +a
mkdir -p /home/a6/.config/mako
cat >/home/a6/.config/mako/config <<CONFIG
font=JetBrains Mono 16
width=580
height=160
anchor=top-center
margin=80,10,10
default-timeout=10000
background-color=#$A6_BG_ALT
text-color=#$A6_FG
border-color=#$A6_ROSE
CONFIG
nohup mako </dev/null >/tmp/a6-mako.private.log 2>&1 &
exec "$panel"

#!/bin/bash
# Bring one phone app into the area between the panel and keyboard.
set -euo pipefail
[[ $(id -u) == 1000 ]]
case "${1:-}" in foot|epiphany) ;; *) exit 2;; esac
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
if [[ -L "$XDG_RUNTIME_DIR/wayland-1" ]]; then
    exec /usr/local/bin/a6-labwc-panel --focus "$1"
fi
for instance in "$XDG_RUNTIME_DIR"/hypr/*; do
 [[ -S "$instance/.socket.sock" ]] || continue
 export HYPRLAND_INSTANCE_SIGNATURE=${instance##*/}
 break
done
exec /usr/local/bin/a6-app-panel --focus "$1"

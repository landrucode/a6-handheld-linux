#!/bin/bash
# User session setup; no synthetic text injection or protocol tracing.
set -euo pipefail
[[ $(id -u) == 1000 ]]
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
ready=0
for ((n=0;n<45;n++)); do
    for instance in "$XDG_RUNTIME_DIR"/hypr/*; do
        [[ -S "$instance/.socket.sock" ]] || continue
        export HYPRLAND_INSTANCE_SIGNATURE=${instance##*/}
        if hyprctl activewindow -j 2>/dev/null | grep -q '"class": "foot"'; then ready=1; break; fi
    done
    (( ready == 0 )) || break
    sleep 1
done
(( ready == 1 ))
# Render/input settings are already loaded from a6-hyprland.lua before startup.
if [[ -f /home/a6/wvkbd-test.pid ]] && kill -0 "$(cat /home/a6/wvkbd-test.pid)" 2>/dev/null; then exit 0; fi
# Theme arguments contain only the public keyboard flags and colour values.
read -r -a theme_args < /usr/local/share/a6/theme/wvkbd.args
nohup /usr/local/bin/wvkbd-native "${theme_args[@]}" --no-popup -H 300 -L 300 -l simple,special --fn "JetBrains Mono 16" </dev/null >/tmp/wvkbd-native.log 2>&1 &
echo $! >/home/a6/wvkbd-test.pid
sleep 1
kill -0 "$(cat /home/a6/wvkbd-test.pid)"

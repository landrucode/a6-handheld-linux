#!/bin/bash
# Run inside the mounted Arch RAM root. Leaves services running on success.
set -euo pipefail
umask 022
mode=${1:-weston}
[[ "$mode" == weston || "$mode" == hyprland || "$mode" == prepare ]]
if [[ "$mode" == hyprland ]]; then
    [[ -x /usr/bin/Hyprland && -x /usr/bin/hyprctl && -r /usr/local/share/a6/hyprland.lua ]]
fi
export XDG_RUNTIME_DIR=/tmp/xdg-runtime WAYLAND_DISPLAY=wayland-a6
export LIBSEAT_BACKEND=seatd LC_ALL=C.UTF-8
[[ -c /dev/dri/card0 && -c /dev/uinput && -r /proc/1/stat ]]
[[ ! -e "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]] || {
    echo 'Wayland socket already exists; inspect the running desktop first.' >&2
    exit 1
}
for process in /proc/[0-9]*/comm; do
    [[ -r "$process" ]] || continue
    read -r name < "$process" || continue
    [[ "$name" != weston && "$name" != Hyprland ]] || { echo 'Compositor already running.' >&2; exit 1; }
done
mkdir -p /run "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
mkdir -p /dev/shm
if ! grep -q ' /dev/shm tmpfs ' /proc/mounts; then
    /proc/1/root/bin/busybox mount -t tmpfs -o size=16m,mode=1777,nosuid,nodev tmpfs /dev/shm
fi
started=()
cleanup() {
    local status=$?
    if (( status != 0 )); then
        for ((i=${#started[@]}-1; i>=0; i--)); do kill "${started[i]}" 2>/dev/null || true; done
    fi
}
trap cleanup EXIT
if [[ ! -S /run/seatd.sock ]]; then
    nohup seatd -l info </dev/null >/tmp/seatd.log 2>&1 &
    started+=("$!")
    for ((i=0;i<50;i++)); do [[ -S /run/seatd.sock ]] && break; sleep 0.1; done
    [[ -S /run/seatd.sock ]]
fi
count=0
for node in /sys/class/input/event*/device/name; do
    [[ -r "$node" ]] || continue
    read -r name < "$node"
    case "$name" in 'A6 USB synthetic keyboard'|'A6 USB synthetic pointer') ((count+=1));; esac
done
if (( count == 0 )); then
    if [[ -e /tmp/a6-input-events ]]; then
        [[ -p /tmp/a6-input-events ]]
    else
        mkfifo -m 600 /tmp/a6-input-events
    fi
    nohup /usr/local/bin/a6-uinput </dev/null >/tmp/a6-uinput.log 2>&1 &
    started+=("$!")
    for ((i=0;i<50;i++)); do grep -q A6_UINPUT_READY /tmp/a6-uinput.log && break; sleep 0.1; done
    grep -q A6_UINPUT_READY /tmp/a6-uinput.log
else
    [[ "$count" == 2 && -p /tmp/a6-input-events ]]
fi
/usr/local/bin/a6-label-input
if [[ "$mode" == prepare ]]; then
    echo A6_SEAT_AND_INPUT_PREPARED
    exit 0
fi
if [[ "$mode" == hyprland ]]; then
    if [[ -r /opt/a6/aquamarine-simpledrm/libaquamarine.so.14 ]]; then
        export LD_LIBRARY_PATH=/opt/a6/aquamarine-simpledrm
    fi
    nohup /bin/bash -c '
        ulimit -c 0
        ulimit -v 524288
        echo 1000 > /proc/self/oom_score_adj
        exec env -u WAYLAND_DISPLAY -u DISPLAY AQ_DRM_DEVICES=/dev/dri/card0 \
            LIBGL_ALWAYS_SOFTWARE=true GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=1 \
            HYPRLAND_NO_CRASHREPORTER=1 Hyprland --i-am-really-stupid \
            --config /usr/local/share/a6/hyprland.lua
    ' </dev/null >/tmp/hyprland-drm.log 2>&1 &
    hyprland_pid=$!
    started+=("$hyprland_pid")
    ready=0
    for ((i=0;i<30;i++)); do
        kill -0 "$hyprland_pid"
        if timeout 2 hyprctl instances | grep -q "pid: $hyprland_pid$"; then ready=1; break; fi
        sleep 0.25
    done
    [[ "$ready" == 1 ]]
    printf 'A6_HYPRLAND_STARTED PID=%s (verify clients and input separately)\n' "$hyprland_pid"
    exit 0
fi
nohup weston --backend=drm --renderer=pixman --shell=kiosk \
    --drm-device=card0 --idle-time=0 --no-config --socket="$WAYLAND_DISPLAY" \
    </dev/null >/tmp/weston-drm.log 2>&1 &
weston_pid=$!
started+=("$weston_pid")
for ((i=0;i<50;i++)); do [[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]] && break; sleep 0.1; done
[[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]]
kill -0 "$weston_pid"
nohup foot /bin/bash </dev/null >/tmp/foot-drm.log 2>&1 &
foot_pid=$!
started+=("$foot_pid")
sleep 1
kill -0 "$weston_pid" "$foot_pid"
printf 'A6_DESKTOP_STARTED Weston=%s Foot=%s\n' "$weston_pid" "$foot_pid"

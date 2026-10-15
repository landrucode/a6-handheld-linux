#!/bin/sh
# RAM-only 24-hour desktop observation with bounded, light per-core checks.
set -eu
umask 077
bb=/bin/busybox
log=/tmp/a6-smp-soak.log
pidfile=/tmp/a6-smp-soak.pid
desktop_pid=${1:?desktop PID required}
case "$desktop_pid" in *[!0-9]*|'') exit 2;; esac
[ "$(cat /proc/$desktop_pid/comm)" = Hyprland ]
[ "$(cat /sys/devices/system/cpu/online)" = 0-1 ]
$bb grep -q 'phase=3 result=0 .*controls=32 ranges=16 full=16' /sys/firmware/a6_smp_bridge/probe_status
[ ! -e "$pidfile" ]
echo "$$" > "$pidfile"
exec >> "$log" 2>&1
trap 'echo A6_SMP_SOAK_V1 aborted; exit 1' HUP INT TERM
printf 'A6_SMP_SOAK_V1 running desktop_pid=%s start_uptime=' "$desktop_pid"
cat /proc/uptime
set -- $($bb sha256sum /tmp/a6-smp-stress.data)
expected=$1
last0=0
last1=0
sample=0
while [ "$sample" -le 1440 ]; do
    printf '\nA6_SOAK_SAMPLE=%s uptime=' "$sample"
    cat /proc/uptime
    if ! kill -0 "$desktop_pid" || [ "$(cat /proc/$desktop_pid/comm)" != Hyprland ]; then
        echo 'A6_SMP_SOAK_V1 failed reason=compositor_missing'; exit 1
    fi
    [ "$(cat /sys/devices/system/cpu/online)" = 0-1 ] || { echo 'A6_SMP_SOAK_V1 failed reason=cpu_offline'; exit 1; }
    for cpu in 0 1; do
        set -- $($bb taskset -c "$cpu" $bb sha256sum /tmp/a6-smp-stress.data)
        [ "$1" = "$expected" ] || { echo "A6_SMP_SOAK_V1 failed reason=hash cpu=$cpu"; exit 1; }
    done
    set -- $($bb awk '/apple-a6-timer$/ {print $2} /apple-a6-timer-cpu1$/ {print $3}' /proc/interrupts)
    [ "$#" = 2 ] && [ "$1" -gt "$last0" ] && [ "$2" -gt "$last1" ] || { echo 'A6_SMP_SOAK_V1 failed reason=timer'; exit 1; }
    last0=$1; last1=$2
    cat /proc/interrupts
    $bb grep -E 'MemAvailable|MemFree|SwapFree' /proc/meminfo
    cat /sys/firmware/a6_charger_policy/status
    cat /sys/firmware/a6_charger_policy/low_battery_status
    $bb grep -q '^auto=1 ' /sys/firmware/a6_charger_policy/status || { echo 'A6_SMP_SOAK_V1 failed reason=auto_off'; exit 1; }
    $bb grep -q '^A6_LOW_BATTERY_CANDIDATE_V3 enabled=1 .*threshold_mv=3600' /sys/firmware/a6_charger_policy/low_battery_status || { echo 'A6_SMP_SOAK_V1 failed reason=monitor'; exit 1; }
    if dmesg | $bb grep -E 'rcu: INFO:|Unable to handle kernel|BUG:|Oops:|Kernel panic'; then
        echo 'A6_SMP_SOAK_V1 failed reason=kernel_log'; exit 1
    fi
    sample=$((sample + 1))
    [ "$sample" -gt 1440 ] || sleep 60
done
echo 'A6_SMP_SOAK_V1 completed_samples=1441'

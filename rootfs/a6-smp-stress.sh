#!/bin/sh
# Short RAM-only two-core hash/fork workload; requires the integration PASS.
set -eu
umask 077
if [ "${1:-}" = worker ]; then
    cpu="$2"
    expected="$3"
    read uptime rest < /proc/uptime
    end=$((${uptime%%.*} + 120))
    loops=0
    while :; do
        read uptime rest < /proc/uptime
        [ "${uptime%%.*}" -lt "$end" ] || break
        set -- $(/bin/busybox sha256sum /tmp/a6-smp-stress.data)
        if [ "$1" != "$expected" ]; then
            echo "FAIL cpu=$cpu loops=$loops hash=$1 expected=$expected"
            exit 1
        fi
        loops=$((loops + 1))
    done
    echo "PASS cpu=$cpu loops=$loops"
    exit 0
fi
/bin/busybox grep -q 'phase=3 result=0 .*controls=32 ranges=16 full=16' /sys/firmware/a6_smp_bridge/probe_status
[ "$(cat /sys/devices/system/cpu/online)" = 0-1 ]
echo "$$" > /tmp/a6-smp-stress.pid
log=/tmp/a6-smp-stress.log
printf 'A6_SMP_STRESS_V1 running\n' > "$log"
cat /proc/uptime >> "$log"
/bin/busybox dd if=/dev/urandom of=/tmp/a6-smp-stress.data bs=65536 count=64 2>> "$log"
set -- $(/bin/busybox sha256sum /tmp/a6-smp-stress.data)
expected="$1"
printf 'expected=%s\n' "$expected" >> "$log"
/bin/busybox taskset -c 0 /bin/busybox sh /tmp/a6-smp-stress.sh worker 0 "$expected" > /tmp/a6-smp-stress-cpu0.log 2>&1 &
p0=$!
/bin/busybox taskset -c 1 /bin/busybox sh /tmp/a6-smp-stress.sh worker 1 "$expected" > /tmp/a6-smp-stress-cpu1.log 2>&1 &
p1=$!
result=0
wait "$p0" || result=1
wait "$p1" || result=1
cat /tmp/a6-smp-stress-cpu0.log /tmp/a6-smp-stress-cpu1.log >> "$log"
cat /proc/interrupts >> "$log"
cat /sys/firmware/a6_charger_policy/status >> "$log"
cat /sys/firmware/a6_charger_policy/low_battery_status >> "$log"
cat /proc/uptime >> "$log"
printf 'A6_SMP_STRESS_V1 result=%s\n' "$result" >> "$log"
exit "$result"

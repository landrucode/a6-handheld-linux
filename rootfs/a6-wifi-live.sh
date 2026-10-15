#!/bin/sh
# Private RAM journal; exported only over the USB-bound recovery server.
# Every sample is complete before atomically replacing the previous one.
# No packet capture, credentials or hardware register reads. Dmesg is private.
umask 077
echo "$$" >/tmp/a6-wifi-live.pid
n=0
wlan_seen=0
while test "$n" -lt 43200; do
    {
        echo A6_WIFI_LIVE_V1 sample="$n"
        cat /proc/uptime
        printf 'STAGE='
        cat /tmp/a6-wifi-stage 2>/dev/null
        cat /sys/firmware/a6_wifi_ehci_enum/progress
        if test -r /sys/firmware/a6_aic/progress; then
            cat /sys/firmware/a6_aic/progress
        fi
        cat /sys/firmware/a6_charger_policy/status
        cat /sys/firmware/a6_charger_policy/low_battery_status
        if test -d /sys/class/net/wlan0; then
            echo WLAN_PRESENT=1
            cat /sys/class/net/wlan0/operstate
            for field in rx_packets tx_packets rx_errors tx_errors; do
                printf "wlan0_%s=" "$field"
                cat /sys/class/net/wlan0/statistics/$field
            done
        else
            echo WLAN_PRESENT=0
        fi
        cat /proc/interrupts
        head -n 8 /proc/meminfo
        dmesg | tail -n 12
    } >/tmp/a6-wifi-live.next 2>&1
    mv /tmp/a6-wifi-live.next /tmp/a6-wifi-live.log
    # Bounded history remains in RAM even while both host transports fail.
    cat /tmp/a6-wifi-live.log >>/tmp/a6-wifi-history.log
    if test "$(wc -c </tmp/a6-wifi-history.log)" -gt 2097152; then
        mv /tmp/a6-wifi-history.log /tmp/a6-wifi-history.previous
    fi
    reason=
    if grep -q '^auto=.* fault=1 ' /tmp/a6-wifi-live.log; then reason=charger; fi
    if test -d /sys/class/net/wlan0; then
        wlan_seen=1
    elif test "$wlan_seen" = 1; then
        reason=wlan-lost
    fi
    if test -n "$reason" && test ! -e /tmp/a6-wifi-incident-$reason.log; then
        {
            cat /tmp/a6-wifi-live.log
            echo INCIDENT_DMESG
            dmesg
            echo INCIDENT_POWER
            tail -n 120 /tmp/a6-power-longrun.log 2>/dev/null
        } >/tmp/a6-wifi-incident-$reason.log
    fi
    n=$((n + 1))
    sleep 1
done

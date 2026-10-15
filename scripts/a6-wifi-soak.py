#!/usr/bin/env python3
"""Log an existing stock connection's USB/charger/driver health privately.

Requests one DHCP renewal and probes inbound ports at the end.
No resets, reloads, or guard changes.
Connection remains running when this collector finishes or detects a fault.
"""
from pathlib import Path
import argparse
import asyncio
import ipaddress
import urllib.request
import importlib.util
import os
import re
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=float, default=4)
    args = parser.parse_args()
    if not 0 < args.hours <= 24:
        parser.error('--hours must be greater than zero and at most 24')
    spec = importlib.util.spec_from_file_location('connection', ROOT/'scripts/a6-wifi-connect.py')
    connection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(connection)
    phone = connection.Phone()
    path = ROOT/'build/session-logs'/('wifi-soak-' + secrets.token_hex(6) + '.private.log')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    # Update the RAM hook in place; the existing DHCP daemon invokes it anew.
    hook = connection.dhcp_hook()
    lease_pattern = r'(?m)^(?:renew|bound) [1-9][0-9]* [0-9]+$'
    baseline = phone.checked('cat ' + connection.REMOTE + '.lease.events 2>/dev/null; true')
    initial_leases = len(re.findall(lease_pattern, baseline))
    phone.evidence.clear()
    phone.upload(hook.encode(), connection.REMOTE + '.dhcp-hook')
    phone.checked('busybox chmod 700 ' + connection.REMOTE + '.dhcp-hook; '
                  'kill -USR1 "$(cat ' + connection.REMOTE + '.dhcp.pid)"')
    print('Requested DHCP renewal; waiting for a successful lease callback', flush=True)
    sample_command = (
        'cat /sys/firmware/a6_charger_policy/status '
        '/sys/firmware/a6_charger_policy/low_battery_status '
        '/sys/firmware/a6_charger_policy/samples; '
        + connection.CLI + ' -p' + connection.REMOTE + '.ctrl -iwlan0 status; '
        + connection.IW + ' dev wlan0 get power_save; '
        'busybox ip neigh show dev wlan0; '
        'for iface in wlan0 usb0; do for field in rx_packets tx_packets '
        'rx_errors tx_errors rx_dropped tx_dropped; do '
        'printf "%s_%s=" "$iface" "$field"; cat /sys/class/net/$iface/statistics/$field; '
        'done; done; cat /proc/meminfo; '
        'cat ' + connection.REMOTE + '.lease.events 2>/dev/null; '
        'busybox tail -n 12 ' + connection.REMOTE + '.dhcp.log; '
        'busybox ping -I wlan0 -c 1 -W 2 "$(cat ' +
        connection.REMOTE + '.gateway)" >/dev/null; echo PING_RC=$?; '
        'echo DMESG_BEGIN; dmesg; echo DMESG_END'
    )
    phone.upload(("#!/bin/sh\n" + sample_command + "\n").encode(), connection.REMOTE + ".soak-sample")
    count = 0
    missed_samples = 0
    consecutive_failures = 0
    previous_dmesg = []
    usb_outages = 0
    usb_failed = False
    renewal_seen = False
    renewal_reported = False
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.monotonic()
    deadline = started + args.hours*3600
    with os.fdopen(fd, 'w', buffering=1) as log:
        while time.monotonic() < deadline:
            log.write('HOST_TIME=' + str(int(time.time())) + '\n')
            try:
                try:
                    with opener.open('http://192.168.7.2:8080/a6-wifi-live.log', timeout=2) as response:
                        if not response.read(64).startswith(b'A6_WIFI_LIVE_V1 '):
                            raise ValueError('Invalid USB journal')
                    if usb_failed:
                        log.write('USB_HTTP_RECOVERED\n')
                    usb_failed = False
                except Exception:
                    if not usb_failed:
                        usb_outages += 1
                        log.write('USB_HTTP_OUTAGE_START\n')
                    usb_failed = True
                log.write('USB_HTTP_OUTAGES=' + str(usb_outages) + '\n')
                output = phone.checked("busybox sh " + connection.REMOTE + ".soak-sample", timeout=30)
                before, sep, rest = output.partition('\nDMESG_BEGIN\n')
                current = rest.rsplit('\nDMESG_END', 1)[0].splitlines() if sep else []
                overlap = min(len(previous_dmesg), len(current))
                while overlap and previous_dmesg[-overlap:] != current[:overlap]:
                    overlap -= 1
                log.write(before + '\nDMESG_DELTA\n' + '\n'.join(current[overlap:]) + '\n')
                previous_dmesg = current
                renewal_seen |= len(re.findall(lease_pattern, before)) > initial_leases
                if renewal_seen and not renewal_reported:
                    renewal_reported = True
                    print('DHCP renewal received a successful lease callback', flush=True)
                phone.evidence.clear()
                count += 1
                consecutive_failures = 0
                if '\nPower save: off\n' not in output:
                    print('Wi-Fi soak detected station power saving enabled; private log retained', flush=True)
                    raise SystemExit(1)
                if '\nwpa_state=COMPLETED\n' not in output or '\nPING_RC=0\n' not in output:
                    print('Wi-Fi soak detected a connection/gateway failure; private log retained', flush=True)
                    raise SystemExit(1)
                if not re.search(r'(?m)^A6_LOW_BATTERY_\S+ enabled=1 .*triggered=0', output) or 'fault=0' not in output:
                    print('Wi-Fi soak detected a battery-policy fault or shutdown trigger; private log retained', flush=True)
                    raise SystemExit(1)
                if re.search(r'(?m)^(?:.*Internal error: Oops|.*BUG:|.*Kernel panic)', output):
                    print('Wi-Fi soak detected a kernel fault; private log retained', flush=True)
                    raise SystemExit(1)
            except Exception as exc:
                log.write('\n'.join(phone.evidence) + '\n')
                log.write('COLLECTOR_FAILURE=' + type(exc).__name__ + '\n')
                missed_samples += 1
                consecutive_failures += 1
                print('USB sample unavailable; retrying in 60 seconds (no reset)', flush=True)
                if consecutive_failures >= 5:
                    print('Wi-Fi soak stopped after five unavailable USB samples', flush=True)
                    raise SystemExit(1)
                time.sleep(min(60, max(0, deadline-time.monotonic())))
                continue
            time.sleep(max(0, min(deadline, started + (count + missed_samples)*60)-time.monotonic()))
        if missed_samples:
            log.write('UNOBSERVED_SAMPLES=' + str(missed_samples) + '\n')
        if not renewal_seen:
            raise RuntimeError('No successful DHCP renewal observed')
        print('Three-hour samples complete; scanning without reloading the firewall', flush=True)
        address_output = phone.checked('cat ' + connection.REMOTE + '.address')
        address = next(str(ipaddress.IPv4Address(line)) for line in address_output.splitlines()
                       if re.fullmatch(r'\d+\.\d+\.\d+\.\d+', line))
        firewall = connection.module('firewall', ROOT/'scripts/a6-wifi-firewall.py')
        opened = asyncio.run(firewall.scan_tcp(address))
        udp = [port for port in firewall.UDP_PORTS
               if firewall.udp_probe(address, port, secrets.token_bytes(24)) is not None]
        log.write('END_SCAN_TCP_OPEN=' + repr(opened) + ' UDP_RESPONSES=' + repr(udp) + '\n')
        log.write(phone.checked(connection.NFT + ' list table ip a6_guard') + '\n')
        phone.listeners()
        if opened or udp:
            raise RuntimeError('End-of-soak inbound scan failed')
    print('End scan passed: 65,535 TCP ports and 12 UDP ports', flush=True)
    print('Wi-Fi soak collected ' + str(count) + ' successful samples; ' +
          str(missed_samples) + ' USB samples unavailable', flush=True)
    if missed_samples:
        raise SystemExit('Soak has observation gaps; continuous three-hour proof incomplete')
    print('Continuous Wi-Fi soak passed', flush=True)


if __name__ == '__main__':
    main()

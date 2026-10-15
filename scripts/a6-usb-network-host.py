#!/usr/bin/env python3
"""Inspect or temporarily configure the A6 USB ECM link; no persistent settings."""
import argparse
import ipaddress
import json
import os
import shutil
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=('status', 'up', 'down'), default='status', nargs='?')
a = p.parse_args()
interfaces = []
for node in Path('/sys/class/net').iterdir():
    if (node / 'address').read_text().strip() != '02:00:00:06:00:01':
        continue
    device = (node / 'device').resolve()
    usb = next((q for q in (device, *device.parents) if (q / 'idVendor').exists()), None)
    if (usb and (device / 'driver').resolve().name == 'cdc_ether'
        and (usb / 'idVendor').read_text().strip() == '0525'
        and (usb / 'idProduct').read_text().strip() == 'a4aa'):
        interfaces.append(node.name)
if len(interfaces) != 1:
    p.error('expected one verified A6 CDC Ethernet interface on any USB port')
interface = interfaces[0]
nm_marker = Path('/run') / ('a6-usb-network-' + interface + '-nm')
print('A6 USB Ethernet:', interface, flush=True)
def run(*args):
    return subprocess.run(args, check=True)
if a.action != 'status':
    if os.geteuid() != 0:
        p.error('up/down requires root; run this specific command with sudo')
    if a.action == 'up':
        routes = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'table', 'all']))
        subnet = ipaddress.ip_network('192.168.7.0/30')
        for route in routes:
            dst = route.get('dst', 'default')
            if dst != 'default' and route.get('dev') != interface and ipaddress.ip_network(dst, strict=False).overlaps(subnet):
                p.error('192.168.7.0/30 overlaps another host route; choose a different subnet first')
        # A DHCP auto-connection can remove an address installed with ip.
        # Override management only at runtime, and remember ownership for down.
        if shutil.which('nmcli'):
            managed = subprocess.run(['nmcli', '-g', 'GENERAL.NM-MANAGED', 'device', 'show', interface], capture_output=True, text=True)
            if managed.returncode == 0 and managed.stdout.strip() == 'yes':
                nm_marker.touch(mode=0o600)
                run('nmcli', 'device', 'set', interface, 'managed', 'no')
        addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', interface]))
        exists = any(x.get('local') == '192.168.7.1' and x.get('prefixlen') == 30 for d in addresses for x in d['addr_info'])
        run('ip', 'link', 'set', 'dev', interface, 'up')
        if not exists:
            run('ip', 'address', 'add', '192.168.7.1/30', 'dev', interface)
    else:
        addresses = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', interface]))
        if any(x.get('local') == '192.168.7.1' and x.get('prefixlen') == 30 for d in addresses for x in d['addr_info']):
            run('ip', 'address', 'del', '192.168.7.1/30', 'dev', interface)
        if nm_marker.exists():
            run('nmcli', 'device', 'set', interface, 'managed', 'reset')
            nm_marker.unlink()
run('ip', '-4', 'address', 'show', 'dev', interface)
print('Phone HTTP: http://192.168.7.2:8080/ (USB-only, no default route added)')

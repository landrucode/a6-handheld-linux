#!/usr/bin/env python3
"""Ten-minute USB comparison and real WLAN downloads on an existing connection.

HTTP is primary; a failed ACM probe latches without recovery/rebinding.
No scans, reassociation, device resets, or battery-policy changes.
"""
import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=float, default=10)
    parser.add_argument('--transport', choices=('http', 'acm'), default='http')
    args = parser.parse_args()
    if not 0 < args.minutes <= 15:
        parser.error('--minutes must be in (0,15]')
    token = Path.home()/'.a6-usb-rpc.token'
    rpc = load('rpc', ROOT/'scripts/a6-usb-http-rpc.py')
    # No fallback or replay: use this transport explicitly throughout.
    if args.transport == 'http':
        os.environ['A6_USB_HTTP_RPC_TOKEN'] = str(token)
    else:
        os.environ.pop('A6_USB_HTTP_RPC_TOKEN', None)
        os.environ['A6_ACM_BROKER'] = str(ROOT/'build/wifi-native/acm.sock')
    connection = load('connection', ROOT/'scripts/a6-wifi-connect.py')
    phone = connection.Phone()
    if args.transport == 'http':
        rpc.capture_incident(token)
    lease_pattern = r'(?m)^(?:bound|renew) [1-9][0-9]* [0-9]+$'
    baseline = phone.checked('cat ' + connection.REMOTE + '.lease.events 2>/dev/null; true')
    initial_leases = len(re.findall(lease_pattern, baseline))
    phone.checked('kill -USR1 "$(cat ' + connection.REMOTE + '.dhcp.pid)"')
    renewed = False
    out = phone.checked('cat ' + connection.REMOTE + '.address')
    address = next(str(ipaddress.IPv4Address(line)) for line in out.splitlines()
                   if re.fullmatch(r'\d+\.\d+\.\d+\.\d+', line))
    route = json.loads(subprocess.check_output(['ip', '-j', 'route', 'get', address]))[0]
    host = str(ipaddress.IPv4Address(route['prefsrc']))
    if host.startswith('192.168.7.') or route['dev'] == 'lo':
        raise RuntimeError('WLAN workload must use the laptop LAN address')
    payload = b'Q' * (1024*1024)
    digest = hashlib.sha256(payload).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.connection.settimeout(10)
            if self.path != '/payload':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    class Server(HTTPServer):
        def handle_error(self, request, client_address):
            pass

    # Only synthetic data; bind the specific LAN address, close on completion.
    server = Server((host, 0), Handler)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log = ROOT/'build/session-logs'/('wifi-quick-' + secrets.token_hex(6) + '.private.log')
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    acm_ok = True
    downloads = samples = 0
    deadline = time.monotonic() + args.minutes*60
    try:
        with os.fdopen(fd, 'w', buffering=1) as stream:
            burst = "busybox head -c 65536 /dev/zero | busybox tr '\\000' Q"
            raw_env = dict(os.environ)
            raw_env.pop('A6_USB_HTTP_RPC_TOKEN', None)
            raw_env['A6_ACM_BROKER'] = str(ROOT/'build/wifi-native/acm.sock')
            # About one MiB per transport, compressing many journal samples.
            for index in range(16 if args.transport == 'http' else 0):
                if time.monotonic() >= deadline:
                    break
                try:
                    rc, body = rpc.execute(burst, token, 10)
                except Exception as error:
                    stream.write('HTTP_BURST_ERROR=' + type(error).__name__ + '\n')
                    raise RuntimeError('HTTP burst failed; command not replayed') from None
                if rc or body != 'Q'*65536:
                    raise RuntimeError('HTTP comparison payload failed')
                if not acm_ok:
                    continue
                marker = 'A6_BURST_END_' + secrets.token_hex(8)
                result = subprocess.run(
                    ['python3', str(ROOT/'scripts/a6-usb-acm-direct.py'),
                     burst + "; printf '\\n'; echo " + marker, '--until', marker, '--timeout', '10'],
                    env=raw_env, capture_output=True, text=True, timeout=20)
                good = result.returncode == 0 and bool(re.search(
                    r'(?:^|\n)Q{65536}\n' + re.escape(marker), result.stdout.replace('\r', '')))
                stream.write('ACM_BURST=' + str(index) + ' PASS=' + str(good) +
                             ' RC=' + str(result.returncode) + ' BYTES=' + str(len(result.stdout)) +
                             ' Q_BYTES=' + str(result.stdout.count('Q')) + '\n')
                if not good:
                    acm_ok = False
                    rpc.capture_incident(token)
                    print('ACM failed; pre-recovery HTTP incident saved; no rebind or reset', flush=True)
            while time.monotonic() < deadline:
                command = (
                    connection.CLI + ' -p' + connection.REMOTE + '.ctrl -iwlan0 status; '
                    'cat ' + connection.REMOTE + '.lease.events; '
                    'cat /sys/firmware/a6_charger_policy/status '
                    '/sys/firmware/a6_charger_policy/low_battery_status; head -n 8 /proc/meminfo; '
                    'busybox ping -I wlan0 -c 3 -W 2 "$(cat ' + connection.REMOTE +
                    '.gateway)" >/dev/null; echo PING_RC=$?; '
                    "printf 'GET /payload HTTP/1.0\\r\\nHost: workload\\r\\n\\r\\n' | busybox timeout 15 " +
                    connection.SOCAT + ' - TCP4:' + host + ':' + str(server.server_port) +
                    ',connect-timeout=5 >/tmp/a6-quick.http && '
                    "busybox sed '1,/^\\r$/d' /tmp/a6-quick.http >/tmp/a6-quick.payload && "
                    "printf '%s  %s\\n' " + digest + ' /tmp/a6-quick.payload | '
                    'busybox sha256sum -c -; echo DOWNLOAD_RC=$?; '
                    'busybox rm -f /tmp/a6-quick.payload /tmp/a6-quick.http')
                if samples == 0:
                    phone.upload(command.encode() + b'\n', '/tmp/a6-quick-workload.sh')
                output = phone.checked('busybox sh /tmp/a6-quick-workload.sh', timeout=25)
                stream.write('HOST_TIME=' + str(int(time.time())) + '\n' + output + '\n')
                phone.evidence.clear()
                if not all(value in output for value in
                           ('wpa_state=COMPLETED', 'PING_RC=0', 'DOWNLOAD_RC=0',
                            'auto=1 paused=0 fault=0')) or not re.search(
                                r'(?m)^A6_LOW_BATTERY_\S+ enabled=1 .*triggered=0', output):
                    raise RuntimeError('Connection/download/power check failed; private output retained')
                renewed |= len(re.findall(lease_pattern, output)) > initial_leases
                samples += 1
                downloads += 1
                time.sleep(min(10, max(0, deadline-time.monotonic())))
            if not renewed:
                raise RuntimeError('No successful DHCP renewal callback observed')
            stream.write('TRANSPORT=' + args.transport + '\n')
            stream.write('SUMMARY_SAMPLES=' + str(samples) + ' DOWNLOADS=' + str(downloads) +
                         ' ACM_PASS=' + str(acm_ok) + '\n')
        print('Quick WLAN test passed: ' + str(downloads) + ' verified one-MiB downloads and ' +
              str(samples*3) + ' gateway pings; ACM comparison ' + ('not run' if args.transport == 'acm' else ('passed' if acm_ok else 'failed')), flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0 if acm_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

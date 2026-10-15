#!/usr/bin/env python3
"""Save the private RAM IRQ journal over USB HTTP during the Wi-Fi trial.

Start before the native host. Uses no ACM endpoint while other scripts run.
No resets or Wi-Fi traffic. Runs at most 24 hours; logs outages privately.
"""
import argparse
import importlib.util
import os
import re
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=float, default=12)
    parser.add_argument('--interval', type=float, default=60)
    args = parser.parse_args()
    if not 0 < args.hours <= 24 or not 1 <= args.interval <= 300:
        parser.error('--hours must be in (0,24]; --interval in [1,300]')
    spec = importlib.util.spec_from_file_location('connection', ROOT/'scripts/a6-wifi-connect.py')
    connection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(connection)
    phone = connection.Phone()
    # Install a RAM-only recovery path before loading firmware or modules.
    token_path = Path.home()/'.a6-usb-rpc.token'
    if not token_path.exists():
        token_fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(token_fd, 'w') as token_file:
            token_file.write(secrets.token_hex(32) + '\n')
    token_stat = token_path.stat()
    if token_stat.st_uid != os.getuid() or token_stat.st_mode & 0o777 != 0o600:
        raise ValueError('RPC token ownership/mode invalid')
    phone.checked('busybox mkdir -p /www/cgi-bin; busybox chmod 0700 /www/cgi-bin')
    phone.upload((ROOT/'rootfs/a6-usb-rpc.cgi').read_bytes(), '/www/cgi-bin/a6-rpc.cgi')
    token = token_path.read_bytes()
    if not re.fullmatch(rb'[0-9a-f]{64}\n', token):
        raise ValueError('RPC token format invalid')
    phone.upload(token, '/tmp/a6-usb-rpc.token', sensitive=True)
    del token
    phone.checked('busybox chmod 0700 /www/cgi-bin/a6-rpc.cgi; busybox chmod 0600 /tmp/a6-usb-rpc.token')
    phone.upload(b'*.cgi:/bin/sh\n', '/etc/httpd.conf')
    phone.upload(b'*.cgi:/bin/sh\n', '/www/httpd.conf')
    phone.checked('for f in /proc/[0-9]*/cmdline; do '
                  'if busybox grep -q httpd "$f"; then '
                  'p=${f#/proc/}; p=${p%/cmdline}; '
                  'test "$p" = "$$" || kill -HUP "$p"; fi; done; true')
    state = phone.checked(
        'if test -f /tmp/a6-wifi-heartbeat.pid && '
        'busybox grep -q a6-wifi-heartbeat /proc/"$(cat /tmp/a6-wifi-heartbeat.pid)"/cmdline; '
        'then echo HEARTBEAT_RUNNING; fi; '
        'if test -f /tmp/a6-wifi-live.pid && '
        'busybox grep -q a6-wifi-live.sh /proc/"$(cat /tmp/a6-wifi-live.pid)"/cmdline; '
        'then echo JOURNAL_RUNNING; fi; true')
    if '\nHEARTBEAT_RUNNING\n' not in state:
        subprocess.run(['bash', str(ROOT/'scripts/build-a6-wifi-heartbeat.sh')], check=True)
        phone.upload((ROOT/'build/wifi-native/heartbeat').read_bytes(), '/tmp/a6-wifi-heartbeat')
        phone.checked('test -w /sys/devices/platform/simple-framebuffer/wifi_heartbeat && '
                      'busybox ln -sf /sys/devices/platform/simple-framebuffer/wifi_heartbeat '
                      '/tmp/a6-wifi-heartbeat-screen && '
                      'busybox chmod 0700 /tmp/a6-wifi-heartbeat; '
                      'echo 0 >/tmp/a6-wifi-stage; '
                      'busybox setsid /tmp/a6-wifi-heartbeat '
                      '</dev/null >/tmp/a6-wifi-heartbeat.log 2>&1 & '
                      'echo $! >/tmp/a6-wifi-heartbeat.pid; sleep 1; '
                      'kill -0 "$(cat /tmp/a6-wifi-heartbeat.pid)"')
    if '\nJOURNAL_RUNNING\n' not in state:
        phone.upload((ROOT/'rootfs/a6-wifi-live.sh').read_bytes(), '/tmp/a6-wifi-live.sh')
        phone.checked('busybox ln -sf /tmp/a6-wifi-live.log /www/a6-wifi-live.log; '
                      'busybox setsid busybox sh /tmp/a6-wifi-live.sh '
                      '</dev/null >/tmp/a6-wifi-live-start.log 2>&1 & sleep 1; '
                      'kill -0 "$(cat /tmp/a6-wifi-live.pid)"')
    path = ROOT/'build/session-logs'/('wifi-live-' + secrets.token_hex(6) + '.private.log')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    print('Independent USB IRQ journal streaming to private host log', flush=True)
    last = None
    with os.fdopen(fd, 'w', buffering=1) as log:
        deadline = time.monotonic() + args.hours*3600
        while time.monotonic() < deadline:
            try:
                # Disable ambient HTTP proxies; use only the point-to-point USB.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open('http://192.168.7.2:8080/a6-wifi-live.log', timeout=2) as response:
                    data = response.read(65537)
                if len(data) > 65536 or not data.startswith(b'A6_WIFI_LIVE_V1 '):
                    raise ValueError('Invalid journal response')
                if data != last:
                    log.write('HOST_TIME=' + str(time.time()) + '\n' + data.decode(errors='replace') + '\n')
                    last = data
            except Exception as exc:
                log.write('HOST_TIME=' + str(time.time()) + ' USB_JOURNAL_ERROR=' + type(exc).__name__ + '\n')
            time.sleep(args.interval)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""RAM-only stock Wi-Fi connection with firewall proof and persistent DHCP.

Credentials are read privately from the owner-only local file, transferred
without saving echoes, and removed from phone RAM immediately after load.
The radio stays up only after the firewall proof succeeds. Disconnect restores
firmware country/MPC and disables data TX without restarting the HSIC host.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import secrets
import shlex
import stat
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/tmp/a6-connection'
USR = '/tmp/a6-native/tools/usr/'
LOADER = USR + 'lib/ld-linux-armhf.so.3 --library-path ' + USR + 'lib '
IW = LOADER + USR + 'bin/iw'
WPA = LOADER + USR + 'bin/wpa_supplicant'
CLI = LOADER + USR + 'bin/wpa_cli'
NFT = LOADER + USR + 'bin/nft'
SS = LOADER + USR + 'bin/ss'
SOCAT = LOADER + USR + 'bin/socat'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def dhcp_hook():
    hook = ('#!/bin/sh\ncase "$1" in\n'
            'deconfig) busybox ip address flush dev wlan0;;\n'
            'bound|renew) busybox ifconfig wlan0 "$ip" netmask "$subnet" || exit 1\n'
            'gateway=${router%% *}\n'
            'test -z "$gateway" || busybox ip route replace default via "$gateway" dev wlan0\n'
            ': >/etc/resolv.conf\n'
            'for resolver in $dns; do printf "nameserver %s\\n" "$resolver" >>/etc/resolv.conf; done\n'
            'printf "%s\\n" "$ip" >' + REMOTE + '.address\n'
            'printf "%s\\n" "$gateway" >' + REMOTE + '.gateway\n'
            'printf "%s %s %s\\n" "$1" "${lease:-0}" "$(busybox date +%s)" >>' + REMOTE + '.lease.events\n'
            ';;\nesac\n')
    return hook


class Phone:
    def __init__(self):
        self.collector = module('collector', ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
        self.codec = module('association', ROOT/'scripts/a6-wifi-associate.py')
        self.evidence = []

    def serial(self, command, timeout=20, sensitive=False):
        try:
            result = self.collector.serial(command, timeout=timeout)
        except Exception:
            # TimeoutExpired includes argv. Never expose an encoded credential
            # through its exception text or the chained traceback.
            self.evidence.append('[serial invocation failed; command omitted]')
            raise RuntimeError('Phone serial invocation failed') from None
        output = (result.stdout + result.stderr).replace('\r', '')
        self.evidence.append('[sensitive transfer output omitted]' if sensitive else output)
        if result.returncode:
            raise RuntimeError('Phone command failed; private evidence retained')
        return output

    def checked(self, command, timeout=20):
        marker = 'CHECKED_' + secrets.token_hex(5)
        split = len(marker)//2
        out = self.serial('(' + command + ") && printf '%s%s\\n' " +
                          marker[:split] + ' ' + marker[split:], timeout)
        if not re.search(r'(?m)^' + marker + '$', out):
            raise RuntimeError('Phone operation failed; private evidence retained')
        return out

    def upload(self, data, path, sensitive=False):
        encoded = base64.b64encode(data).decode()
        self.checked('umask 077; : > ' + path + '.b64')
        try:
            for offset in range(0, len(encoded), 320):
                self.serial("printf '%s' " + encoded[offset:offset+320] +
                            ' >> ' + path + '.b64', sensitive=sensitive)
            self.checked('busybox base64 -d ' + path + '.b64 > ' + path +
                         ' && busybox chmod 600 ' + path + ' && ' +
                         "printf '%s  %s\\n' " + hashlib.sha256(data).hexdigest() +
                         ' ' + path + ' | busybox sha256sum -c -')
        finally:
            self.serial('busybox rm -f ' + path + '.b64')

    def vendor(self, name, length, value=None):
        body = name.encode() + b'\0'
        if value is None:
            body = body.ljust(max(length, len(body)), b'\0')
            command, size, setting = 262, length, 0
        else:
            body += value
            command, size, setting = 263, len(body), 1
        raw = struct.pack('<IIIII', command, size, 20, setting, 0) + body
        self.upload(raw, REMOTE + '.ioctl')
        out = self.checked(IW + ' dev wlan0 vendor recv 0x001018 0x1 ' + REMOTE + '.ioctl')
        return self.codec.vendor_payload(out, length) if value is None else None

    def install_firewall(self):
        # Resolve direct module dependencies from the build manifest, rather
        # than relying on an uninstalled /lib/modules modprobe database.
        import json
        dependency_file = ROOT/'build/wifi-native/firewall-modules.json'
        for name in json.loads(dependency_file.read_text()):
            self.checked('test -d /sys/module/' + name.replace('-', '_') +
                         ' || busybox insmod /tmp/a6-native/modules/' + name + '.ko')
        existing = self.serial(NFT + ' list table ip a6_guard 2>/dev/null')
        policy = (ROOT/'rootfs/a6-wifi.nft').read_bytes()
        if re.search(r'(?m)^table ip a6_guard ', existing):
            # nft applies this replacement in one transaction: no empty-policy
            # interval, including repeated attempts within the same boot.
            policy = b'delete table ip a6_guard\n' + policy
        self.upload(policy, REMOTE + '.nft')
        self.checked(NFT + ' -f ' + REMOTE + '.nft')
        self.checked(NFT + ' list table ip a6_guard; test ! -e /proc/net/if_inet6')
        print('Default-deny inbound firewall installed before radio UP; IPv6 absent')

    def listeners(self):
        out = self.checked(SS + ' -H -ltnup')
        listeners = []
        for line in out.splitlines():
            fields = line.split()
            if fields and fields[0] in ('tcp', 'udp'):
                if len(fields) < 6:
                    raise RuntimeError('Unrecognized socket inspection output')
                local = fields[4]
                # No wildcard or Wi-Fi management listeners. DHCP client
                # port 68 is a necessary, narrowly filtered protocol endpoint.
                if local.rsplit(':', 1)[-1] == '68' and fields[0] == 'udp':
                    listeners.append('DHCP client')
                elif local.startswith(('127.0.0.1:', '192.168.7.2:')):
                    listeners.append('loopback/USB')
                else:
                    raise RuntimeError('Unexpected inbound listener; private socket evidence retained')
        print('Socket inspection passed: recovery on USB; no Wi-Fi management listener')
        return listeners

    def disconnect(self):
        boot = self.serial('test ! -f /tmp/a6-connection.country.original || echo BOOT_DEFAULT_CONNECTION')
        if '\nBOOT_DEFAULT_CONNECTION\n' in boot:
            self.checked('busybox sh /etc/a6-wifi-off.sh')
            print('Boot Wi-Fi disabled; country/MPC restored by readback')
            return
        out = self.checked('for kind in watchdog dhcp wpa; do f=' + REMOTE +
                     '.$kind.pid; test ! -f "$f" || kill "$(cat "$f")" 2>/dev/null || :; done; '
                     'sleep 1; busybox ip link set wlan0 down && '
                     'busybox ip address flush dev wlan0 && '
                     'echo N > /sys/module/brcmfmac/parameters/a6_allow_data_tx && '
                     'busybox rm -f ' + REMOTE + '.conf ' + REMOTE + '.conf.b64 && '
                     'busybox ip -o link show wlan0')
        if any(': wlan0:' in line and '<' in line and 'UP' in
               line.split('<', 1)[1].split('>', 1)[0].split(',') for line in out.splitlines()):
            raise RuntimeError('Radio DOWN readback failed')
        out = self.serial('busybox base64 ' + REMOTE + '.original')
        values = [line for line in out.splitlines() if re.fullmatch(r'[A-Za-z0-9+/]{22}==', line)]
        if len(values) != 1:
            raise RuntimeError('Original firmware setting record missing')
        original = base64.b64decode(values[0], validate=True)
        country, mpc = original[:12], original[12:]
        self.vendor('country', 12, country)
        self.vendor('mpc', 4, mpc)
        if self.vendor('country', 12) != country or self.vendor('mpc', 4) != mpc:
            raise RuntimeError('Firmware setting restoration failed')
        self.checked('test "$(cat /sys/module/brcmfmac/parameters/a6_allow_data_tx)" = N && '
                     '(test ! -f ' + REMOTE + '.dhcp.pid || ! kill -0 "$(cat ' + REMOTE +
                     '.dhcp.pid)" 2>/dev/null) && (test ! -f ' + REMOTE +
                     '.wpa.pid || ! kill -0 "$(cat ' + REMOTE + '.wpa.pid)" 2>/dev/null) && '
                     'busybox rm -f ' + REMOTE + '.connected ' + REMOTE + '.original ' +
                     REMOTE + '.address ' + REMOTE + '.wpa.pid ' + REMOTE + '.dhcp.pid ' +
                     REMOTE + '.watchdog.pid')
        print('Disconnected: radio down, data TX disabled, country/MPC restored by readback')


def connect(phone, config):
    with config.open('rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise RuntimeError('Configuration must be owned by the current user, mode 600')
        configuration = stream.read(65537)
    if not configuration or len(configuration) > 65536:
        raise RuntimeError('Configuration size refused')
    pre = phone.checked('echo 7 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; test -d /sys/class/net/wlan0 && '
                  'test -d /sys/module/af_packet && '
                  'test "$(cat /sys/module/brcmfmac/parameters/a6_allow_data_tx)" = N && '
                  'test "$(cat /sys/module/brcmfmac/parameters/a6_tx_hsic_header)" = N && '
                  'test ! -f ' + REMOTE + '.original && busybox ip -o link show wlan0')
    if any(': wlan0:' in line and '<' in line and 'UP' in
           line.split('<', 1)[1].split('>', 1)[0].split(',') for line in pre.splitlines()):
        raise RuntimeError('wlan0 must start down')
    health = phone.serial('cat /sys/firmware/a6_charger_policy/status '
                          '/sys/firmware/a6_charger_policy/low_battery_status')
    if 'auto=1 paused=0 fault=0' not in health or not re.search(r'(?m)^A6_LOW_BATTERY_\S+ enabled=1 .*triggered=0', health):
        raise RuntimeError('Battery policy precondition failed')
    phone.upload((ROOT/'rootfs/a6-power-longrun.sh').read_bytes(), '/tmp/a6-power-longrun.sh')
    phone.checked('if test -f /tmp/a6-power-longrun.pid && '
                  'kill -0 "$(cat /tmp/a6-power-longrun.pid)" 2>/dev/null; then :; '
                  'else busybox setsid busybox sh /tmp/a6-power-longrun.sh '
                  '</dev/null >/tmp/a6-power-longrun-start.log 2>&1 & sleep 1; fi; '
                  'test -f /tmp/a6-power-longrun.pid && kill -0 "$(cat /tmp/a6-power-longrun.pid)"')
    phone.install_firewall()
    phone.listeners()
    # Set host-derived time before any wireless connection/TLS use.
    phone.checked('busybox date -s @' + str(int(time.time())) + ' >/dev/null')
    original = phone.vendor('country', 12) + phone.vendor('mpc', 4)
    phone.upload(original, REMOTE + '.original')
    keep = False
    try:
        phone.vendor('country', 12, b'GB\0\0' + struct.pack('<i', -1) + b'GB\0\0')
        country = phone.vendor('country', 12)
        if country[:4] != b'GB\0\0' or country[8:] != b'GB\0\0':
            raise RuntimeError('GB country readback failed')
        print('Firmware GB country confirmed, revision ' + str(struct.unpack('<i', country[4:8])[0]))
        phone.vendor('mpc', 4, b'\0'*4)
        if phone.vendor('mpc', 4) != b'\0'*4:
            raise RuntimeError('MPC disable readback failed')
        phone.upload(configuration, REMOTE + '.conf', sensitive=True)
        del configuration
        # Startup/gate failure closes the radio independently of the laptop.
        # The connection is promoted to persistent only when all gates pass.
        watchdog = ('sleep 300; for kind in dhcp wpa; do f=' + REMOTE +
                    '.$kind.pid; test ! -f "$f" || kill "$(cat "$f")"; done; '
                    'busybox ip link set wlan0 down; echo N > '
                    '/sys/module/brcmfmac/parameters/a6_allow_data_tx; busybox rm -f ' + REMOTE + '.conf')
        phone.checked('busybox setsid busybox sh -c ' + shlex.quote(watchdog) +
                      ' </dev/null >/dev/null 2>&1 & echo $! >' + REMOTE + '.watchdog.pid')
        phone.checked('echo Y > /sys/module/brcmfmac/parameters/a6_allow_data_tx && '
                      'busybox ip link set wlan0 up && ' + IW +
                      ' dev wlan0 set power_save off')
        power_save = phone.checked(IW + ' dev wlan0 get power_save')
        if not re.search(r'(?m)^Power save: off$', power_save):
            raise RuntimeError('Wi-Fi power saving disable readback failed')
        phone.checked(WPA +
                      ' -B -Dnl80211 -iwlan0 -c' + REMOTE + '.conf -C' + REMOTE +
                      '.ctrl -P' + REMOTE + '.wpa.pid >/dev/null 2>&1')
        phone.checked('busybox rm -f ' + REMOTE + '.conf; test ! -e ' + REMOTE + '.conf')
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            out = phone.checked(CLI + ' -p' + REMOTE + '.ctrl -iwlan0 status')
            if '\nwpa_state=COMPLETED\n' in out:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Association did not complete within 45 seconds')
        print('Stock wlan0 association completed; credential file removed from RAM')
        hook = dhcp_hook()
        phone.upload(hook.encode(), REMOTE + '.dhcp-hook')
        phone.checked('busybox chmod 700 ' + REMOTE + '.dhcp-hook; '
                      'busybox setsid busybox udhcpc -f -n -i wlan0 -t 3 -T 3 -p ' +
                      REMOTE + '.dhcp.pid -s ' + REMOTE + '.dhcp-hook </dev/null >' +
                      REMOTE + '.dhcp.log 2>&1 & echo DHCP_STARTED')
        deadline = time.monotonic() + 18
        address = None
        while time.monotonic() < deadline:
            out = phone.serial('test ! -f ' + REMOTE + '.address || cat ' + REMOTE + '.address')
            values = [line for line in out.splitlines() if re.fullmatch(r'\d+\.\d+\.\d+\.\d+', line)]
            if values:
                address = str(ipaddress.IPv4Address(values[-1]))
                break
            time.sleep(1)
        if not address:
            raise RuntimeError('DHCP failed within its bound')
        phone.checked('busybox ping -I wlan0 -c 3 -W 2 "$(cat ' + REMOTE + '.gateway)" >/dev/null', timeout=12)
        print('DHCP and gateway pings passed; renewal daemon running')
        firewall = module('firewall', ROOT/'scripts/a6-wifi-firewall.py')
        phone.checked('echo 8 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo')
        firewall.prove(phone.checked, address, NFT, SOCAT, phone.evidence)
        phone.listeners()
        phone.checked('kill "$(cat ' + REMOTE + '.watchdog.pid)" && '
                      'kill -0 "$(cat ' + REMOTE + '.wpa.pid)" && '
                      'kill -0 "$(cat ' + REMOTE + '.dhcp.pid)" && '
                      'touch ' + REMOTE + '.connected && echo 9 >/tmp/a6-wifi-stage')
        manifest = json.loads((ROOT/'build/wifi-native/manifest.json').read_text())
        keep = manifest.get('hardening') is True
        if keep:
            print('Firewall gate passed; stock wlan0 left connected with DHCP renewal')
        else:
            print('Firewall proof passed on hardening diagnostic; disconnecting after test')
    finally:
        if not keep:
            phone.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('connect', 'status', 'disconnect'))
    parser.add_argument('--config', type=Path, default=Path.home()/'.a6-wifi.conf')
    args = parser.parse_args()
    phone = Phone()
    try:
        if args.action == 'connect':
            connect(phone, args.config)
        elif args.action == 'disconnect':
            phone.disconnect()
        else:
            out = phone.checked(CLI + ' -p' + REMOTE + '.ctrl -iwlan0 status')
            match = re.search(r'(?m)^wpa_state=(\w+)$', out)
            print('WPA state:', match[1] if match else 'unavailable')
            phone.checked(NFT + ' list table ip a6_guard')
            phone.listeners()
    finally:
        log = ROOT/'build/session-logs'/('wifi-connection-' + secrets.token_hex(6) + '.private.log')
        log.write_text('\n'.join(phone.evidence))
        log.chmod(0o600)


if __name__ == '__main__':
    main()

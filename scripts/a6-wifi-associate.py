#!/usr/bin/env python3
"""Bounded RAM-only native WPA trial. Run only after explicit transmit approval.

Reads the local configuration without displaying it. Optional --dhcp tests a
lease and local gateway, without a default route or DNS changes. Stops
supplicant, brings wlan0 down, disables data TX and restores
country/MPC after success or failure. Private evidence stays in ignored build/.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import os
import re
import secrets
import base64
import stat
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = '/tmp/a6-native/tools/usr/'
LOADER = TOOLS + 'lib/ld-linux-armhf.so.3 --library-path ' + TOOLS + 'lib '
IW = LOADER + TOOLS + 'bin/iw'
WPA = LOADER + TOOLS + 'bin/wpa_supplicant'
CLI = LOADER + TOOLS + 'bin/wpa_cli'


def vendor_payload(output, length):
    """Extract DATA netlink attributes from iw's hex output without identities."""
    chunks = []
    lines = re.findall(r'(?m)^vendor response: ([0-9a-f ]+)', output)
    # iw repeats this prefix at each 16-byte display boundary, including
    # boundaries inside a netlink attribute. Decode the whole reply first.
    for data in [bytes.fromhex(' '.join(lines))]:
        offset = 0
        while offset + 4 <= len(data):
            size, kind = struct.unpack_from('<HH', data, offset)
            if size < 4 or offset + size > len(data):
                raise RuntimeError('Malformed vendor reply')
            if kind == 2:
                chunks.append(data[offset + 4:offset + size])
            offset += (size + 3) & ~3
    body = b''.join(chunks)
    if len(body) != length:
        raise RuntimeError('Vendor reply length mismatch')
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--associate', action='store_true', required=True,
                        help='Execute only with explicit user transmit approval')
    parser.add_argument('--config', type=Path, default=Path.home()/'.a6-wifi.conf')
    parser.add_argument('--dhcp', action='store_true',
                        help='After association, test DHCP and local gateway only')
    parser.add_argument('--capture', action='store_true',
                        help='Use the pre-staged RAM packet capture helper during DHCP')
    parser.add_argument('--stop-host', action='store_true',
                        help='Release native HSIC ownership after cleanup, before log reads')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        'collector', ROOT/'scripts/a6-capture-wifi-ehci-enum.py')
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    nonce = secrets.token_hex(6)
    evidence = []
    remote = '/tmp/a6-wpa-' + nonce
    country = mpc = None
    touched = False
    staged = False

    def serial(command, timeout=20, sensitive=False):
        try:
            result = collector.serial(command, timeout=timeout)
        except Exception:
            evidence.append('[serial invocation failed; command omitted]')
            raise RuntimeError('Phone serial invocation failed') from None
        output = (result.stdout + result.stderr).replace('\r', '')
        evidence.append('[sensitive transfer output omitted]' if sensitive else output)
        if result.returncode:
            raise RuntimeError('Phone command timed out; inspect private evidence')
        return output

    def vendor(name, length, value=None):
        body = name.encode() + b'\0'
        if value is None:
            body = body.ljust(max(length, len(body)), b'\0')
            command, size, setting = 262, length, 0
        else:
            body += value
            command, size, setting = 263, len(body), 1
        raw = struct.pack('<IIIII', command, size, 20, setting, 0) + body
        encoded = ''.join('\\x%02x' % byte for byte in raw)
        output = serial("printf '" + encoded + "' > " + remote + '.ioctl; ' +
                        IW + ' dev wlan0 vendor recv 0x001018 0x1 ' +
                        remote + '.ioctl; echo VENDOR_RC=$?')
        if '\nVENDOR_RC=0\n' not in output:
            raise RuntimeError('Firmware control command failed')
        return vendor_payload(output, length) if value is None else None

    def packet_counts(label):
        # Same WLC_GET_GET_PKTCNTS ABI used by stock brcmfmac station stats;
        # retain the reply even if older firmware refuses this read-only query.
        raw = struct.pack('<IIIII', 137, 20, 20, 0, 0) + b'\0' * 20
        encoded = ''.join('\\x%02x' % byte for byte in raw)
        output = serial("printf '" + encoded + "' > " + remote + '.counts; ' +
                        IW + ' dev wlan0 vendor recv 0x001018 0x1 ' +
                        remote + '.counts; echo COUNTS_RC=$?')
        if '\nCOUNTS_RC=0\n' in output:
            values = struct.unpack('<IIIII', vendor_payload(output, 20))
            evidence.append('FIRMWARE_PACKET_COUNTS_' + label + '=' + repr(values))

    try:
        pre = serial('cat /sys/module/brcmfmac/parameters/a6_allow_data_tx; '
                     'test ! -d /sys/module/af_packet || echo PACKET_READY; '
                     'cat /sys/firmware/a6_charger_policy/status; '
                     'cat /sys/firmware/a6_charger_policy/low_battery_status; '
                     'busybox ip -o link show wlan0')
        if '\nN\n' not in pre or 'auto=1 paused=0 fault=0' not in pre:
            raise RuntimeError('Native data TX or battery policy precondition failed')
        if '\nPACKET_READY\n' not in pre:
            raise RuntimeError('AF_PACKET module is required for supplicant')
        if not re.search(r'(?m)^A6_LOW_BATTERY_\S+ enabled=1 .*triggered=0', pre):
            raise RuntimeError('Battery shutdown monitor precondition failed')
        if any(': wlan0:' in line and '<' in line and
               'UP' in line.split('<', 1)[1].split('>', 1)[0].split(',')
               for line in pre.splitlines()):
            raise RuntimeError('wlan0 must start down')
        country = vendor('country', 12)
        if country[:4] != b'GB\0\0' or country[8:] != b'GB\0\0':
            raise RuntimeError('Firmware GB regulation is not confirmed')
        mpc = vendor('mpc', 4)
        # The file is read only when this explicitly invoked trial starts.
        with args.config.open('rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise RuntimeError('Configuration must be owned by current user, mode 600')
            configuration = stream.read(65537)
        if not configuration or len(configuration) > 65536:
            raise RuntimeError('Configuration size refused')
        digest = hashlib.sha256(configuration).hexdigest()
        staged = True
        # Avoid USB-network bulk uploads while the native HSIC host is alive:
        # repeated small config uploads have coincided with whole-phone stalls.
        # Credential-transfer echoes must never enter saved evidence.
        encoded = base64.b64encode(configuration).decode()
        del configuration
        serial('umask 077; : > ' + remote + '.conf.part.b64')
        for offset in range(0, len(encoded), 400):
            serial("printf '%s' " + encoded[offset:offset + 400] +
                   ' >> ' + remote + '.conf.part.b64', sensitive=True)
        del encoded
        output = serial('busybox base64 -d ' + remote + '.conf.part.b64 > ' +
                        remote + '.conf.part && busybox chmod 600 ' + remote +
                        '.conf.part && busybox rm -f ' + remote + '.conf.part.b64 && '
                        "printf '%s  %s\\n' " + digest + ' ' + remote +
                        '.conf.part | busybox sha256sum -c - && busybox mv ' +
                        remote + '.conf.part ' + remote + '.conf && echo CONFIG_VERIFIED')
        if '\nCONFIG_VERIFIED\n' not in output:
            raise RuntimeError('RAM configuration transfer failed')
        touched = True
        vendor('mpc', 4, struct.pack('<I', 0))
        if vendor('mpc', 4) != b'\0' * 4:
            raise RuntimeError('MPC disable readback failed')
        # An independent phone timer limits radio activity if host USB hangs.
        watchdog = ('sleep ' + ('75' if args.dhcp else '60') + '; test -f ' + remote + '.pid && kill "$(cat ' +
                    remote + '.pid)"; busybox ip link set wlan0 down; '
                    'echo N > /sys/module/brcmfmac/parameters/a6_allow_data_tx')
        output = serial("busybox setsid busybox sh -c '" + watchdog +
                        "' </dev/null >" + remote + '.watchdog.log 2>&1 & echo $! > ' +
                        remote + '.watchdog.pid; echo Y > /sys/module/brcmfmac/parameters/a6_allow_data_tx; '
                        'busybox ip link set wlan0 up && ' + WPA +
                        ' -B -Dnl80211 -iwlan0 -c' + remote + '.conf -C' +
                        remote + '.ctrl -P' + remote + '.pid -f' + remote +
                        '.log; echo WPA_RC=$?')
        if '\nWPA_RC=0\n' not in output:
            raise RuntimeError('Supplicant startup failed')
        deadline = time.monotonic() + 45
        state = 'UNKNOWN'
        while time.monotonic() < deadline:
            output = serial(CLI + ' -p' + remote + '.ctrl -iwlan0 status')
            match = re.search(r'(?m)^wpa_state=(\w+)$', output)
            if match:
                state = match[1]
            if state == 'COMPLETED':
                print('WPA association completed')
                if args.dhcp:
                    serial('echo STATION_BEFORE; ' + IW + ' dev wlan0 station dump')
                    packet_counts('BEFORE')
                    if args.capture:
                        serial('busybox setsid /tmp/a6-capture </dev/null > ' + remote +
                               '.capture.log 2>&1 & echo $! > ' + remote + '.capture.pid; sleep 1')
                    # Configure only the leased local address, without installing
                    # a default route or changing the USB route/DNS configuration.
                    hook = ('#!/bin/sh\ncase "$1" in\n'
                            'bound|renew) busybox ifconfig wlan0 "$ip" netmask "$subnet"; '
                            'printf "%s\\n" "$router" > ' + remote + '.gateway;;\nesac\n')
                    encoded = base64.b64encode(hook.encode()).decode()
                    output = serial("printf '%s' " + encoded + ' | busybox base64 -d > ' +
                                    remote + '.dhcp-hook; busybox chmod 700 ' + remote +
                                    '.dhcp-hook; busybox timeout 12 busybox udhcpc -i wlan0 '
                                    '-n -q -t 3 -T 3 -s ' + remote + '.dhcp-hook > ' +
                                    remote + '.dhcp.log 2>&1; echo DHCP_RC=$?')
                    if '\nDHCP_RC=0\n' in output:
                        print('DHCP lease acquired')
                        output = serial('gateway=$(busybox cut -d " " -f 1 ' + remote +
                                        '.gateway); test -n "$gateway" && busybox ping '
                                        '-I wlan0 -c 3 -W 2 "$gateway" > ' + remote +
                                        '.ping.log 2>&1; echo GATEWAY_RC=$?')
                        print('Local gateway ping ' + ('passed' if '\nGATEWAY_RC=0\n' in output else 'failed'))
                    else:
                        print('DHCP did not acquire a lease within its bound')
                    serial('echo STATION_AFTER; ' + IW + ' dev wlan0 station dump')
                    packet_counts('AFTER')
                break
            time.sleep(1)
        else:
            print('WPA association did not complete within 45 seconds; final state ' + state)
    finally:
        try:
            if touched:
                if args.capture:
                    serial('test ! -f ' + remote + '.capture.pid || kill "$(cat ' +
                           remote + '.capture.pid)"; cat ' + remote + '.capture.log 2>/dev/null')
                output = serial('test ! -f ' + remote + '.pid || kill "$(cat ' +
                                remote + '.pid)"; sleep 1; busybox ip link set wlan0 down; '
                                'busybox ip addr flush dev wlan0; '
                                'echo N > /sys/module/brcmfmac/parameters/a6_allow_data_tx; '
                                'cat /sys/module/brcmfmac/parameters/a6_allow_data_tx; '
                                'busybox ip -o link show wlan0')
                if '\nN\n' not in output or any(
                    ': wlan0:' in line and '<' in line and
                    'UP' in line.split('<', 1)[1].split('>', 1)[0].split(',')
                    for line in output.splitlines()):
                    raise RuntimeError('Radio cleanup readback failed')
                vendor('country', 12, country)
                vendor('mpc', 4, mpc)
                if vendor('country', 12) != country or vendor('mpc', 4) != mpc:
                    raise RuntimeError('Country/MPC restoration readback failed')
                serial('test ! -f ' + remote + '.watchdog.pid || kill "$(cat ' +
                       remote + '.watchdog.pid)"; echo RESTORE_VERIFIED')
                print('Cleanup verified: interface down, data TX disabled, country/MPC restored')
            if staged:
                serial('busybox rm -f ' + remote + '.conf ' + remote + '.conf.part ' + remote + '.conf.part.b64')
            if touched:
                if args.stop_host:
                    output = serial('cat /sys/class/net/wlan0/statistics/rx_packets '
                                    '/sys/class/net/wlan0/statistics/tx_packets; '
                                    'echo stop-native-n42-wlan > /sys/firmware/a6_wifi_ehci_enum/run; '
                                    'cat /sys/firmware/a6_wifi_ehci_enum/native', timeout=110)
                    if '\nA6_WIFI_NATIVE_V1 active=0 result=0 restore=0\n' not in output:
                        raise RuntimeError('Native HSIC release failed')
                    print('Native HSIC host stopped and platform state restored')
                serial('test ! -f ' + remote + '.log || cat ' + remote + '.log')
                if args.dhcp:
                    serial('cat ' + remote + '.dhcp.log ' + remote + '.ping.log 2>/dev/null; '
                           'test ! -d /sys/class/net/wlan0 || cat '
                           '/sys/class/net/wlan0/statistics/rx_packets '
                           '/sys/class/net/wlan0/statistics/tx_packets')
        finally:
            log = ROOT/'build/session-logs'/('wifi-native-associate-' + nonce + '.private.log')
            log.write_text('\n'.join(evidence))
            log.chmod(0o600)


if __name__ == '__main__':
    main()

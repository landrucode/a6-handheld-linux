#!/usr/bin/env python3
"""Run one attended WLAN-only EHCI trial and retain evidence on the host."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = '/sys/firmware/a6_wifi_ehci_enum'

def serial(command, timeout=20):
    marker = 'A6_ENUM_END_' + secrets.token_hex(8)
    return subprocess.run([sys.executable, str(ROOT / 'scripts/a6-usb-acm-direct.py'),
        command + '; echo ' + marker, '--until', marker, '--timeout', str(timeout)],
        capture_output=True, text=True, timeout=timeout + 10, check=False)

def classify(output):
    if re.search(r'(?m)^Internal error: Oops', output):
        return 'kernel_oops_restoration_unverified'
    lines = [line for line in output.replace('\r', '').splitlines()
             if re.match(r'A6_WIFI_EHCI_ENUM_V[12] attempted=', line)]
    if not lines and re.search(r'(?m)^trial_inflight=1\r?$', output):
        return 'trial_inflight_restoration_unverified'
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous enumeration status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if fields.get('attempted') != '1':
        return 'not_run'
    legacy = lines[0].startswith('A6_WIFI_EHCI_ENUM_V1 ')
    if legacy and fields.get('stage') == '2' and fields.get('result') == '-22' and fields.get('restore') == '-22':
        # Audited V1 rejects 0x72 before TX; PHY/gate final values were not captured.
        return 'software_write_refused_restoration_unverified'
    if fields.get('stage') == '0':
        return 'preflight_refused'
    if not legacy and fields.get('restore') == '0':
        required = ('reset_readback', 'reset72_after', 'gate_before', 'gate_after',
                    'phy8_after', 'usb_ctl_after', 'pmu_submitted',
                    'pmu_restore_submitted', 'pmu_completed', 'pmu_restore_completed')
        if any(key not in fields for key in required):
            return 'restoration_unverified'
        if (fields['reset_readback'] != '0' or
            fields['reset72_after'] != fields.get('reset72') or
            fields['gate_after'] != fields['gate_before'] or
            (int(fields['phy8_after'], 16) & 0x20) != (int(fields['phy8'], 16) & 0x20) or
            (int(fields['usb_ctl_after'], 16) & 4) != (int(fields['usb_ctl'], 16) & 4)):
            return 'restoration_failed'
        if fields.get('result') == '-22' and fields['pmu_submitted'] == '0':
            return 'software_write_refused_restored'
    if not legacy and fields.get('restore') == '-22' and fields.get('pmu_restore_submitted') == '0':
        return 'software_restore_write_refused_restoration_unverified'
    if fields.get('restore') != '0':
        return 'restoration_failed'
    if fields.get('stage') == '0':
        return 'preflight_refused'
    if fields.get('result') == '0' and fields.get('vid') not in ('0000', None):
        return 'usb_device_enumerated'
    return 'no_enumeration_restored'

def classify_identity(output):
    enumeration = classify(output)
    if enumeration != 'usb_device_enumerated':
        return enumeration
    lines = [line for line in output.replace('\r', '').splitlines()
             if line.startswith('A6_WIFI_USB_IDENTITY_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous boot-ROM identity status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if fields.get('enabled') != '1':
        return 'identity_query_disabled'
    if fields.get('result') != '0':
        return 'identity_query_failed_restored'
    length = int(fields['length'])
    if (length < 8 or length > 24 or length % 4 or
        int(fields['fields'], 16) != (1 << (length // 4)) - 1 or
        fields.get('submitted') != '1' or
        any(fields.get(key) != value for key, value in
            (('request', '05'), ('type', 'c1'), ('value', '0001'), ('index', '0000')))):
        return 'identity_response_invalid_restored'
    if int(fields['chip'], 16) in (0, 0xffffffff, 0xdead):
        return 'identity_response_invalid_restored'
    return 'bootrom_identity_read'

def classify_otp(output):
    identity = classify_identity(output)
    if identity != 'bootrom_identity_read':
        return identity
    identity_lines = [line for line in output.splitlines()
                      if line.startswith('A6_WIFI_USB_IDENTITY_V1 enabled=')]
    identity_fields = dict(re.findall(r'(\w+)=([^ ]+)', identity_lines[0]))
    required_identity = {'length': '24', 'fields': '3f', 'chip': '00004334',
                         'chiprev': '00000003', 'ramsize': '00080000',
                         'remapbase': '60000000'}
    if any(identity_fields.get(k) != v for k, v in required_identity.items()):
        return 'otp_identity_mismatch_restored'
    lines = [line for line in output.splitlines()
             if line.startswith('A6_WIFI_USB_OTP_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous OTP status')
    fields = dict(re.findall(r'(\w+)=([^ ]*)', lines[0]))
    if fields.get('enabled') != '1':
        return 'otp_query_disabled'
    if fields.get('result') != '0':
        return 'otp_query_failed_restored'
    try:
        size, start, end, submitted, completed = [int(fields[k]) for k in
            ('bytes', 'start', 'end', 'submitted', 'completed')]
    except (KeyError, ValueError):
        return 'otp_response_invalid_restored'
    if (not 0 < size <= 512 or size & 1 or (start | end) & 1 or
        not 0 <= start < end <= 0x1fff or end-start != size or
        submitted != completed or completed != size // 2 + 2 or
        fields.get('request') != '11' or fields.get('type') != 'c1' or
        fields.get('reply_bytes') != '16' or fields.get('data_word') != '3' or
        not re.fullmatch('[0-9a-f]{' + str(2*size) + '}', fields.get('data', ''))):
        return 'otp_response_invalid_restored'
    return 'bootrom_otp_read'

def classify_download(output):
    otp = classify_otp(output)
    if otp != 'bootrom_otp_read':
        return otp
    lines = [line for line in output.splitlines()
             if line.startswith('A6_WIFI_USB_DOWNLOAD_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous firmware download status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if fields.get('enabled') != '1':
        return 'firmware_download_disabled'
    if fields.get('result') != '0':
        return 'firmware_download_failed_restored'
    try:
        expected, sent, received, submitted, completed, cs, cc = [int(fields[k]) for k in
            ('expected', 'sent', 'rom_bytes', 'bulk_submitted', 'bulk_completed',
             'control_submitted', 'control_completed')]
        endpoint = int(fields['endpoint'], 16)
    except (KeyError, ValueError):
        return 'firmware_download_invalid_restored'
    if (expected != 456108 or sent != expected or received != expected or
        submitted != completed or completed != 305 or cs != cc or not 3 <= cs <= 12 or
        fields.get('state') != '4' or fields.get('go_submitted') != '0' or not 1 <= endpoint <= 15):
        return 'firmware_download_invalid_restored'
    return 'firmware_download_runnable_restored'

def classify_execute(output):
    download = classify_download(output)
    if download != 'firmware_download_runnable_restored':
        return download
    lines = [line for line in output.replace('\r', '').splitlines()
             if line.startswith('A6_WIFI_USB_EXECUTE_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous firmware execution status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if fields.get('enabled') != '1':
        return 'firmware_execution_disabled'
    if fields.get('gpio_writes') != '0' and (fields.get('gpio_restore') != '0' or
        fields.get('gpio_after') != fields.get('gpio_saved')):
        return 'firmware_execution_gpio_restoration_failed'
    if (fields.get('result') == '-110' and fields.get('go_submitted') == '1' and
        fields.get('go_completed') == '1' and fields.get('reset') == '-19' and
        fields.get('getver_submitted') == '0'):
        return 'firmware_reenumeration_timeout_restored'
    if fields.get('result') != '0':
        return 'firmware_execution_failed_restored'
    if (fields.get('go_submitted') != '1' or fields.get('go_completed') != '1' or
        fields.get('reset') not in ('0', '-19') or fields.get('getver_submitted') != '1' or
        fields.get('getver_length') not in ('8', '12', '16', '20', '24') or
        fields.get('chip') != '0000a123' or fields.get('gpio_writes') != '4' or
        fields.get('gpio_restore') != '0' or fields.get('gpio_after') != fields.get('gpio_saved')):
        return 'firmware_execution_invalid_restored'
    return 'firmware_runtime_identity_restored'

def classify_runtime(output):
    execution = classify_execute(output)
    if execution != 'firmware_runtime_identity_restored':
        return execution
    lines = [line for line in output.replace('\r', '').splitlines()
             if line.startswith('A6_WIFI_USB_RUNTIME_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous runtime transport status')
    fields = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    required = {'enabled': '1', 'result': '0', 'tx': '3', 'rx': '3',
                'completed': '3', 'chip': '17204', 'chiprev': '3'}
    if any(fields.get(k) != v for k, v in required.items()):
        return 'firmware_runtime_transport_failed_restored'
    if fields.get('ioctl') not in ('1', '2') or not 1 <= int(fields.get('version_bytes', '0')) < 256:
        return 'firmware_runtime_transport_invalid_restored'
    if 'resume error' in output or 'reset error' in output or 'A6 IRQ restart bound' in output:
        return 'firmware_runtime_transport_passed_hsic_errors_restored'
    return 'firmware_runtime_transport_hsic_restored'

def classify_bulk_rx(output, loopback=False):
    runtime = classify_runtime(output)
    if runtime != 'firmware_runtime_transport_hsic_restored':
        return runtime
    lines = [line for line in output.replace('\r', '').splitlines()
             if line.startswith('A6_WIFI_USB_BULK_RX_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous bulk receive status')
    f = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if f.get('registered') != f.get('deregistered') or (f.get('claimed') != '0' and
        (f.get('release') != '0' or f.get('disconnected') != f.get('claimed'))):
        return 'bulk_rx_driver_release_unverified'
    required = {'enabled': '1', 'attempted': '1', 'registered': '1', 'deregistered': '1',
                'claimed': '1', 'disconnected': '1', 'release': '0', 'submitted': '1', 'tx': '1' if loopback else '0', 'mps': '512'}
    if any(f.get(k) != v for k,v in required.items()):
        return 'bulk_rx_failed_restored'
    try:
        endpoint_in, endpoint_out, received, frames, payload = (
            int(f['in'],16), int(f['out'],16), int(f['bytes']), int(f['frames']), int(f['payload']))
    except (KeyError,ValueError):
        return 'bulk_rx_invalid_restored'
    if not (0x81 <= endpoint_in <= 0x8f and 1 <= endpoint_out <= 15):
        return 'bulk_rx_invalid_restored'
    if f.get('result') == '-110' and f.get('usb_result') == '-110' and received == frames == payload == 0:
        return 'bulk_rx_quiet_timeout_restored'
    if f.get('result') != '0' or f.get('usb_result') != '0':
        return 'bulk_rx_failed_restored'
    if not (18 <= received <= 2048 and frames == 1 and 14 <= payload <= received - 4):
        return 'bulk_rx_invalid_restored'
    return 'bulk_rx_frame_observed_restored'

def classify_loopback(output):
    lines = [line for line in output.replace('\r', '').splitlines()
             if line.startswith('A6_WIFI_USB_LOOPBACK_V1 enabled=')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous loopback status')
    f = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if f.get('restore') != '0':
        return 'bulk_loopback_not_proven_restore_unverified'
    base = classify_bulk_rx(output, loopback=True)
    if base != 'bulk_rx_frame_observed_restored':
        return base
    required = {'enabled': '1', 'result': '0', 'attempted': '1', 'ctl_tx': '4',
                'ctl_rx': '4', 'out': '1', 'echo': '1', 'before': '0', 'after': '0',
                'radio_up': '0'}
    try:
        bounded = 1 <= int(f['in']) <= 16 and int(f['skipped']) + int(f['other']) == int(f['in']) - 1 and 86 <= int(f['bytes']) <= 32864
    except (KeyError, ValueError):
        bounded = False
    if not bounded or any(f.get(k) != v for k, v in required.items()):
        return 'bulk_loopback_not_proven_restored'
    return 'bulk_loopback_echo_observed_restored'

def classify_scan(output):
    base = classify_runtime(output)
    if base != 'firmware_runtime_transport_hsic_restored':
        return base
    lines = [l for l in output.replace('\r', '').splitlines() if l.startswith('A6_WIFI_USB_SCAN_V1 ')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous scan status')
    f = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if any(f.get(k) != v for k,v in {'enabled':'1','passive':'1','association':'0','bulk_out':'0'}.items()):
        return 'firmware_scan_contract_unverified'
    for attempted,result in [('country_attempted','country_restore'),('mask_attempted','mask_restore'),('up_attempted','down'),('start_attempted','abort'),('mpc_attempted','mpc_restore')]:
        if f.get(attempted) == '1' and f.get(result) != '0':
            return 'firmware_scan_cleanup_unverified'
    if f.get('release') != '0' or f.get('registered') != '1' or f.get('deregistered') != '1':
        return 'firmware_scan_cleanup_unverified'
    if f.get('result') != '0' or f.get('complete') != '1':
        return 'firmware_scan_not_proven_restored'
    return 'firmware_scan_BSS_observed_restored' if int(f.get('partials','0')) else 'firmware_scan_completion_only_restored'

def classify_preflight(output, country=False):
    base = classify_runtime(output)
    if base != 'firmware_runtime_transport_hsic_restored':
        return base
    lines = [l for l in output.replace('\r', '').splitlines() if l.startswith('A6_WIFI_USB_PREFLIGHT_V1 ')]
    if len(lines) != 1:
        raise RuntimeError('Missing or ambiguous preflight status')
    f = dict(re.findall(r'(\w+)=([^ ]+)', lines[0]))
    if country:
        if f.get('country_trial_enabled') != '1':
            return 'firmware_country_mode_unverified'
        if f.get('country_attempted') == '1' and f.get('country_restore') != '0':
            return 'firmware_country_restore_unverified'
        if f.get('country_result') != '0':
            return 'firmware_country_not_proven'
    required = {'enabled':'1', 'attempted':'1', 'tx':'9' if country else '4', 'rx':'9' if country else '4', 'radio_up':'0', 'set':'2' if country else '0', 'bulk_out':'0'}
    if country:
        required['country_attempted'] = '1'
    if any(f.get(k) != v for k,v in required.items()):
        return 'firmware_preflight_incomplete_restored'
    if f.get('result') != '0' or any(f.get(k) != '0' for k in ('country','clm','mac','channels')):
        return 'firmware_preflight_query_failure_restored'
    return 'firmware_country_readbacks_original_restored' if country else 'firmware_preflight_readbacks_restored'

def build_capture_command(stem, identity=False, otp=False, download=False, execute=False, runtime=False, rx=False, loopback=False, preflight=False):
    if not re.fullmatch(r'/tmp/a6-ehci-[0-9a-f]{16}', stem):
        raise ValueError('invalid RAM evidence stem')
    paths = '$b/status' + (' $b/identity' if identity else '') + \
            (' $b/otp' if otp else '') + (' $b/download' if download else '') + (' $b/execute' if execute else '') + (' $b/runtime' if runtime else '') + (' $b/bulk_rx' if rx else '') + (' $b/loopback' if loopback else '') + (' $b/preflight' if preflight else '')
    # BusyBox's interactive input line is bounded; reserve completion printf
    # overhead as well as the command. Fixed aliases avoid repeated paths.
    command = ('b=' + BASE + '; s=' + stem + '; '
               '(echo enumerate-once-n42-wlan > $b/run; echo probe_write_rc=$?; '
               'cat ' + paths + '; echo done > $s.done) > $s.out 2>&1 & '
               'n=0; while [ ! -f $s.done ] && [ "$n" -lt ' +
               ('90' if execute else '70' if download else '45') + ' ]; do '
               'cat $b/progress; sleep 1; n=$((n+1)); done; '
               'cat $b/progress $s.out; '
               'if [ ! -f $s.done ]; then echo trial_inflight=1; fi; '
               'cat /proc/interrupts; dmesg | busybox grep -E '
               '"A6_WIFI|A6_EHCI|A6_HSIC|A6 IRQ|usb |ehci|Unable to handle|Internal error:|Workqueue:|PC is at|pc :|Call trace:|Function entered"; '
               'cat /sys/firmware/a6_charger_policy/status '
               '/sys/firmware/a6_charger_policy/low_battery_status')
    if len(command.encode()) > 900:
        raise ValueError('capture command exceeds bounded shell line budget')
    return command

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', action='store_true',
                        help='require the opt-in GETVER identity candidate')
    parser.add_argument('--download', action='store_true',
                        help='require opt-in ROM firmware download; never execute firmware')
    parser.add_argument('--otp', action='store_true',
                        help='require the opt-in stock OTP read; save private evidence under build/')
    parser.add_argument('--execute', action='store_true',
                        help='require bounded GO/host-ready/reset/runtime GETVER candidate')
    parser.add_argument('--runtime', action='store_true', help='require read-only BCDC transport and HSIC checks')
    parser.add_argument('--rx', action='store_true', help='require one passive runtime bulk-IN observation')
    parser.add_argument('--loopback', action='store_true', help='require one bounded bus-only bulk echo and mode readback')
    parser.add_argument('--preflight', action='store_true', help='four read-only scan prerequisite GETs; no radio/scan')
    parser.add_argument('--country', action='store_true', help='explicit GB SET/readback/channel query and original-country restoration; no UP/scan')
    parser.add_argument('--scan', action='store_true', help='explicit isolated passive GB escan, no association/netdev; restore original settings')
    args = parser.parse_args()
    if args.scan:
        if args.preflight or args.country or args.loopback:
            parser.error('scan excludes preflight/country/loopback')
        args.rx = True
    if args.country:
        args.preflight = True
    if args.preflight and (args.rx or args.loopback):
        parser.error('read-only preflight excludes RX/loopback')
    if args.preflight:
        args.runtime = True
    if args.loopback:
        args.rx = True
    if args.rx:
        args.runtime = True
    if args.runtime:
        args.execute = True
    if args.execute:
        args.download = True
    if args.download:
        args.otp = True
    if args.otp:
        args.identity = True
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = ROOT / 'build/session-logs' / (stamp + '-ehci-enum-' + secrets.token_hex(4))
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence = []
    report = {'classification': 'incomplete', 'captured_at_utc': stamp}
    try:
        pre = serial('cat /sys/firmware/a6_charger_policy/status; '
                     'cat /sys/firmware/a6_charger_policy/low_battery_status; '
                     'cat ' + BASE + '/status; cat ' + BASE + '/progress' +
                     ('; cat ' + BASE + '/identity' if args.identity else '') +
                     ('; cat ' + BASE + '/otp' if args.otp else '') +
                     ('; cat ' + BASE + '/download; busybox sha256sum /lib/firmware/a6-centennial-tdk.trx'
                      if args.download else '') + '; if [ -f ' + BASE + '/execute ]; then cat ' + BASE + '/execute; fi' +
                     '; if [ -f ' + BASE + '/runtime ]; then cat ' + BASE + '/runtime; fi' +
                     '; if [ -f ' + BASE + '/bulk_rx ]; then cat ' + BASE + '/bulk_rx; fi' +
                     '; if [ -f ' + BASE + '/loopback ]; then cat ' + BASE + '/loopback; fi' +
                     '; if [ -f ' + BASE + '/preflight ]; then cat ' + BASE + '/preflight; fi')
        evidence.append(pre.stdout + pre.stderr)
        if pre.returncode:
            raise RuntimeError('ACM preflight failed')
        auto = re.search(r'(?m)^auto=[^\r\n]*', pre.stdout)
        low = re.search(r'A6_LOW_BATTERY_CANDIDATE_V3[^\r\n]*', pre.stdout)
        for line, required in ((auto, ('auto=1', 'paused=0', 'fault=0', 'attached=1')),
                               (low, ('enabled=1', 'attended_trial=0',
                                      'attended_plugged=0', 'threshold_mv=3600'))):
            if not line or any(not re.search(r'(?:^| )' + field + r'(?: |$)', line.group())
                               for field in required):
                raise RuntimeError('Power protection preflight refused')
        if not re.search(r'(?m)^A6_WIFI_EHCI_ENUM_V2 attempted=[01] ', pre.stdout):
            raise RuntimeError('Enumeration endpoint absent')
        if not re.search(r'(?m)^A6_EHCI_PROGRESS_V1 phase=(?:0|8) ', pre.stdout):
            raise RuntimeError('Diagnostic progress endpoint absent or still running')
        if args.identity and not re.search(r'(?m)^A6_WIFI_USB_IDENTITY_V1 enabled=1 ', pre.stdout):
            raise RuntimeError('Identity candidate absent; no trial submitted')
        if args.otp and not re.search(r'(?m)^A6_WIFI_USB_OTP_V1 enabled=1 ', pre.stdout):
            raise RuntimeError('OTP candidate absent; no trial submitted')
        if args.download and not re.search(r'(?m)^A6_WIFI_USB_DOWNLOAD_V1 enabled=1 ', pre.stdout):
            raise RuntimeError('Download candidate absent; no trial submitted')
        execution = re.search(r'(?m)^A6_WIFI_USB_EXECUTE_V1 enabled=([01]) ', pre.stdout)
        if args.execute and (not execution or execution.group(1) != '1'):
            raise RuntimeError('Execution candidate absent; no trial submitted')
        if not args.execute and execution and execution.group(1) == '1':
            raise RuntimeError('Execution-enabled image requires explicit --execute; no trial submitted')
        runtime = re.search(r'(?m)^A6_WIFI_USB_RUNTIME_V1 enabled=([01]) ', pre.stdout)
        if args.runtime and (not runtime or runtime.group(1) != '1'):
            raise RuntimeError('Runtime candidate absent; no trial submitted')
        if not args.runtime and runtime and runtime.group(1) == '1':
            raise RuntimeError('Runtime-enabled image requires explicit --runtime; no trial submitted')
        rx = re.search(r'(?m)^A6_WIFI_USB_BULK_RX_V1 enabled=([01]) ', pre.stdout)
        if args.rx and (not rx or rx.group(1) != '1'):
            raise RuntimeError('Bulk receive candidate absent; no trial submitted')
        if not args.rx and rx and rx.group(1) == '1':
            raise RuntimeError('Bulk-receive image requires explicit --rx; no trial submitted')
        loop = re.search(r'(?m)^A6_WIFI_USB_LOOPBACK_V1 enabled=([01]) ', pre.stdout)
        if args.loopback and (not loop or loop.group(1) != '1'):
            raise RuntimeError('Loopback candidate absent; no trial submitted')
        if not args.loopback and loop and loop.group(1) == '1':
            raise RuntimeError('Loopback-enabled image requires explicit --loopback; no trial submitted')
        scan_mode = re.search(r'(?m)^A6_WIFI_USB_SCAN_V1 enabled=([01]) ', pre.stdout)
        if args.scan and (not scan_mode or scan_mode.group(1) != '1'):
            raise RuntimeError('Scan candidate absent; no trial submitted')
        if not args.scan and scan_mode and scan_mode.group(1) == '1':
            raise RuntimeError('Scan-enabled image requires explicit --scan; no trial submitted')
        pref = re.search(r'(?m)^A6_WIFI_USB_PREFLIGHT_V1 enabled=([01]) ', pre.stdout)
        if args.preflight and (not pref or pref.group(1) != '1'):
            raise RuntimeError('Preflight candidate absent; no trial submitted')
        if not args.preflight and pref and pref.group(1) == '1':
            raise RuntimeError('Preflight image requires explicit --preflight; no trial submitted')
        country_mode = re.search(r'(?m)^A6_WIFI_USB_PREFLIGHT_V1 .* country_trial_enabled=([01]) ', pre.stdout)
        if args.country and (not country_mode or country_mode.group(1) != '1'):
            raise RuntimeError('Country candidate absent; no trial submitted')
        if not args.country and country_mode and country_mode.group(1) == '1':
            raise RuntimeError('Country-enabled image requires explicit --country; no trial submitted')
        if args.download:
            package = json.loads((ROOT / 'build/wifi-firmware/a6-download-package.json').read_text())
            if not re.search(r'(?m)^' + re.escape(package['sha256']) +
                             r'  /lib/firmware/a6-centennial-tdk\.trx\r?$', pre.stdout):
                raise RuntimeError('RAM firmware SHA256 absent/mismatched; no trial submitted')
            report['firmware_package_sha256'] = package['sha256']
        stem = '/tmp/a6-ehci-' + secrets.token_hex(8)
        # Leave the foreground shell available if a USB-core call blocks.
        # Never read the mutex-protected final status until the writer returns.
        command = build_capture_command(stem, args.identity, args.otp, args.download, args.execute, args.runtime, args.rx, args.loopback, args.preflight or args.scan)
        report['ram_evidence_stem'] = stem
        run = serial(command, timeout=115 if args.execute else 100 if args.download else 80)
        evidence.append(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError('ACM enumeration capture failed')
        report['classification'] = (classify_scan(run.stdout) if args.scan else
                                    classify_preflight(run.stdout, country=args.country) if args.preflight else
                                    classify_loopback(run.stdout) if args.loopback else
                                    classify_bulk_rx(run.stdout) if args.rx else
                                    classify_runtime(run.stdout) if args.runtime else
                                    classify_execute(run.stdout) if args.execute else
                                    classify_download(run.stdout) if args.download else
                                    classify_otp(run.stdout) if args.otp else
                                    classify_identity(run.stdout) if args.identity
                                    else classify(run.stdout))
        if args.scan and not re.search(r'(?m)^trial_inflight=1\r?$', run.stdout):
            capture = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-capture-wifi-scan.py')], capture_output=True, text=True, timeout=35)
            report['private_scan_capture_returncode'] = capture.returncode
            if capture.returncode == 0:
                report['private_scan_capture'] = json.loads(capture.stdout)
            else:
                report['private_scan_capture_error'] = 'Snapshot collection failed; private console retained'
        if args.preflight and not re.search(r'(?m)^trial_inflight=1\r?$', run.stdout):
            capture = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-capture-wifi-preflight.py')], capture_output=True, text=True, timeout=35)
            report['private_preflight_capture_returncode'] = capture.returncode
            if capture.returncode == 0:
                report['private_preflight_capture'] = json.loads(capture.stdout)
            else:
                report['private_preflight_capture_error'] = 'Snapshot collection failed; private console preserved'
        if args.loopback and not re.search(r'(?m)^trial_inflight=1\r?$', run.stdout):
            capture = subprocess.run([sys.executable, str(ROOT / 'scripts/a6-capture-wifi-rx-packet.py'),
                                      '--loopback'], capture_output=True, text=True, timeout=35)
            report['private_loopback_capture_returncode'] = capture.returncode
            if capture.returncode == 0:
                report['private_loopback_capture'] = json.loads(capture.stdout)
            else:
                report['private_loopback_capture_error'] = 'Snapshot collection failed; private console retained under build/session-logs'
        print(report['classification'])
    except subprocess.TimeoutExpired as exc:
        for value in (exc.stdout, exc.stderr):
            evidence.append(value.decode(errors='replace') if isinstance(value, bytes)
                            else value or '')
        report['error'] = 'ACM timeout'
        raise
    except BaseException as exc:
        report['error'] = str(exc)
        raise
    finally:
        prefix.with_suffix('.console.txt').write_text('\n'.join(evidence))
        prefix.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
        print('Evidence: ' + str(prefix.with_suffix('.json')))

if __name__ == '__main__':
    main()

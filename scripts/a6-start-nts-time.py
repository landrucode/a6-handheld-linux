#!/usr/bin/env python3
"""Deliver the verified NTS runtime over Wi-Fi or paced USB and start it in phone RAM."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selected-update', action='store_true')
    parser.add_argument('--usb-images', action='store_true', help='Use paced USB after provisioning fallback')
    args = parser.parse_args()
    output = ROOT / 'build/time-runtime'
    bundle = output / 'runtime.tar.gz'
    expected = (output / 'runtime.sha256').read_text().strip()
    if args.selected_update:
        import json
        selected = ROOT / json.loads((ROOT / 'build/ram-updates/selection.json').read_text())['current']
        spec = importlib.util.spec_from_file_location('updater', ROOT / 'scripts/manage-a6-ram-update.py')
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)
        data = updater.verify(selected)
        bundle = selected / 'time-runtime.tar.gz'
        expected = data['files']['time-runtime.tar.gz']
    if hashlib.file_digest(bundle.open('rb'), 'sha256').hexdigest() != expected:
        raise ValueError('Prepared NTS runtime changed')
    os.environ.pop('A6_USB_HTTP_RPC_TOKEN', None)
    os.environ['A6_ACM_BROKER'] = str(ROOT / 'build/wifi-native/acm.sock')
    spec = importlib.util.spec_from_file_location('provision', ROOT / 'scripts/a6-provision-boot.py')
    provision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provision)
    phone = provision.module('connection', ROOT / 'scripts/a6-wifi-connect.py').Phone()
    try:
        phone.checked('test ! -d /tmp/a6-time-runtime && test ! -d /tmp/a6-time && '
                      'busybox mkdir -m 700 /tmp/a6-time-runtime')
        transport='usb' if args.usb_images else 'wifi'
        print('NTS runtime image_transport='+transport,flush=True)
        phone.evidence.append('NTS runtime image_transport='+transport)
        provision.deliver_image(phone,transport,bundle,'/tmp/a6-time-runtime.tar.gz',expected)
        ca=Path('/etc/ssl/cert.pem')
        provision.deliver_image(phone,transport,ca,'/tmp/a6-time-ca.pem',hashlib.file_digest(ca.open('rb'),'sha256').hexdigest())
        phone.checked('busybox mv /tmp/a6-time-ca.pem /tmp/a6-time-runtime/ca-bundle.pem')
        phone.checked('busybox tar -xzf /tmp/a6-time-runtime.tar.gz -C /tmp/a6-time-runtime')
        phone.upload((ROOT / 'rootfs/a6-start-nts-time.sh').read_bytes(), '/tmp/a6-start-nts-time.sh')
        phone.checked('busybox setsid busybox sh /tmp/a6-start-nts-time.sh </dev/null '
                      '>/tmp/a6-time-start.private.log 2>&1 &')
        print('RAM NTS startup requested; verify authenticated selection through chronyc.')
    finally:
        path = ROOT / 'build/session-logs/nts-provision.private.log'
        path.write_text('\n'.join(phone.evidence))
        path.chmod(0o600)


if __name__ == '__main__':
    main()

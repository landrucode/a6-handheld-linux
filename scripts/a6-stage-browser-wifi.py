#!/usr/bin/env python3
"""Fetch the sole signed browser over Wi-Fi, with the paced USB fallback."""
import importlib.util,json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def main():
    os.umask(0o077)
    provision=load('provision',ROOT/'scripts/a6-provision-boot.py')
    updater=load('updater',ROOT/'scripts/manage-a6-ram-update.py')
    bundle=ROOT/json.loads((ROOT/'build/ram-updates/selection.json').read_text())['current']
    release=updater.verify(bundle)
    phone=provision.module('connection',ROOT/'scripts/a6-wifi-connect.py').Phone()
    try:
        transport,reason=provision.choose_image_transport(phone)
        record='browser image_transport='+transport+' reason='+reason
        print(record,flush=True);phone.evidence.append(record)
        provision.deliver_image(phone,transport,bundle/'browser.squashfs','/tmp/a6-browser-images/browser.squashfs',release['files']['browser.squashfs'])
        print('Selected signed browser image staged and hash verified')
    finally:
        path=ROOT/'build/session-logs'/('browser-stage-'+str(time.time_ns())+'.private.log')
        path.write_text('\n'.join(phone.evidence));path.chmod(0o600)
if __name__=='__main__':main()

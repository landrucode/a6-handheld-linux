#!/usr/bin/env python3
"""Stage matching native modules in phone RAM; load/start or stop explicitly.

No interface UP, scan, association, credential reading or data TX enablement.
Hardware startup uses the existing battery guards and loader.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,secrets,socket,time
ROOT=Path(__file__).resolve().parents[1]
BASE='/sys/firmware/a6_wifi_ehci_enum'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('start','stop','restart'));p.add_argument('--headerless-tx',action='store_true',help='Use proven BDC-only data TX (default)');p.add_argument('--headed-tx',action='store_true',help='Experimental 16-byte TX header mode');a=p.parse_args()
 if a.headerless_tx and a.headed_tx:p.error('Choose one TX header mode')
 spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/a6-capture-wifi-ehci-enum.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 evidence=[];nonce=secrets.token_hex(6)
 def serial(cmd,timeout=20):
  r=m.serial(cmd,timeout=timeout);evidence.append(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError('USB native command failed; private log retained')
  return r.stdout.replace('\r','')
 try:
  if a.action in ('stop','restart'):
   s=serial('echo stop-native-n42-wlan > '+BASE+'/run; cat '+BASE+'/native '+BASE+'/status',timeout=110)
   if 'active=0 result=0 restore=0\n' not in s:raise RuntimeError('Native stop/restoration failed')
   if a.action=='stop':print('Native host stopped; PMU/PHY/clock restored');return
   s=serial('busybox rmmod brcmfmac_wcc; busybox rmmod brcmfmac; cat /proc/modules')
   if any(l.startswith(('brcmfmac ', 'brcmfmac_wcc ')) for l in s.splitlines()):raise RuntimeError('Old native driver remains loaded after stop')
  pre=serial('echo 3 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; cat '+BASE+'/native; uname -r; test -d /sys/class/net/wlan0 && echo WLAN_ALREADY_PRESENT')
  if 'A6_WIFI_NATIVE_V1 active=' not in pre:raise RuntimeError('Native host image absent')
  if 'WLAN_ALREADY_PRESENT\n' in pre:print('Native wlan0 already present; no startup repeated');return
  if 'A6_WIFI_NATIVE_V1 active=1' in pre:raise RuntimeError('Host active without wlan0; inspect private evidence before stop/restart')
  artifact=ROOT/'build/wifi-native/modules.tar.gz';data=artifact.read_bytes();digest=hashlib.sha256(data).hexdigest()
  release=(ROOT/'build/wifi-native/kernel.release').read_text().strip()
  if '\n'+release+'\n' not in pre:raise RuntimeError('Matching native kernel release absent')
  package=json.loads((ROOT/'build/wifi-native/manifest.json').read_text())
  if package['sha256']!=digest:raise RuntimeError('Native module package changed since build')
  if package.get('image_sha256')!=hashlib.sha256((ROOT/'build/arm/a6-wifi-brcmfmac.img3').read_bytes()).hexdigest():raise RuntimeError('Native image/package mismatch')
  cached=serial('busybox sha256sum /tmp/a6-native.tar.gz 2>/dev/null')
  if digest+'  /tmp/a6-native.tar.gz' not in cached:
   worker='umask 077; busybox timeout 40 busybox nc -l -p 8085 192.168.7.2 > /tmp/a6-native.tar.gz; echo $? > /tmp/a6-native-'+nonce+'.status'
   serial("busybox setsid busybox sh -c '"+worker+"' </dev/null >/tmp/a6-native-stage.log 2>&1 & echo MODULE_LISTENING")
   deadline=time.monotonic()+5
   while True:
    try:connection=socket.create_connection(('192.168.7.2',8085),timeout=2);break
    except ConnectionRefusedError:
     if time.monotonic()>deadline:raise
     time.sleep(.1)
   with connection:
    connection.settimeout(15)
    for i in range(0,len(data),65536):connection.sendall(data[i:i+65536]);time.sleep(.0625)
    connection.shutdown(socket.SHUT_WR)
  s=serial("echo 4 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; sleep 1; printf '%s  %s\\n' "+digest+' /tmp/a6-native.tar.gz | busybox sha256sum -c - && busybox mkdir -p /tmp/a6-native && busybox tar -xzf /tmp/a6-native.tar.gz -C /tmp/a6-native && busybox mkdir -p /lib/firmware && busybox cp /tmp/a6-native/tools/usr/lib/firmware/regulatory.db* /lib/firmware/ && echo MODULE_PACKAGE_VERIFIED')
  if 'MODULE_PACKAGE_VERIFIED\n' not in s:raise RuntimeError('RAM module package validation failed')
  # Vendor module registers with brcmfmac before runtime-ready handoff.
  load='; '.join('test -d /sys/module/'+n.replace('-','_')+' || busybox insmod /tmp/a6-native/modules/'+n+'.ko'+(' a6_tx_hsic_header=1' if n=='brcmfmac' and a.headed_tx else '') for n in ('sha256','af_packet','cfg80211','brcmutil','brcmfmac','brcmfmac-wcc'))
  s=serial('echo 5 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; '+load+'; cat /proc/modules; echo MODULES_LOADED',timeout=110)
  for n in ('sha256','af_packet','cfg80211','brcmutil','brcmfmac','brcmfmac_wcc'):
   if not any(l.startswith(n+' ') for l in s.splitlines()):raise RuntimeError('Native module did not load: '+n)
  tx=serial('cat /sys/module/brcmfmac/parameters/a6_allow_data_tx')
  if '\nN\n' not in tx:raise RuntimeError('Native data TX is not disabled')
  mode=serial('cat /sys/module/brcmfmac/parameters/a6_tx_hsic_header')
  if ('\nY\n' if a.headed_tx else '\nN\n') not in mode:raise RuntimeError('Loaded N42 TX header mode differs from requested mode')
  stem='/tmp/a6-native-'+nonce
  cmd='echo 6 >/tmp/a6-wifi-stage; head -n 8 /proc/meminfo; (echo start-native-n42-wlan > '+BASE+'/run; echo $? > '+stem+'.rc) > '+stem+'.out 2>&1 & n=0; while test ! -f '+stem+'.rc && test "$n" -lt 90; do sleep 1; n=$((n+1)); done; cat '+stem+'.rc '+stem+'.out '+BASE+'/native; test -d /sys/class/net/wlan0 && echo WLAN_PRESENT; dmesg | busybox tail -n 100'
  s=serial(cmd,timeout=110)
  if 'A6_WIFI_NATIVE_V1 active=1 result=0 restore=-115\n' not in s:raise RuntimeError('Native startup failed or is still running')
  if 'WLAN_PRESENT\n' not in s:raise RuntimeError('Native host retained but wlan0 absent; private probe log retained')
  s=serial('busybox ip link set wlan0 down; busybox ip -o link show wlan0')
  if any(': wlan0:' in l and '<' in l and 'UP' in l.split('<',1)[1].split('>',1)[0].split(',') for l in s.splitlines()):raise RuntimeError('Native interface remains up')
  s=serial('/tmp/a6-native/tools/usr/lib/ld-linux-armhf.so.3 --library-path /tmp/a6-native/tools/usr/lib /tmp/a6-native/tools/usr/bin/iw dev')
  if not any(l.strip()=='Interface wlan0' for l in s.splitlines()):raise RuntimeError('iw cannot enumerate native wlan0')
  print('Native brcmfmac created wlan0 and iw enumerated it; interface down, data TX disabled')
 finally:
  log=ROOT/'build/session-logs'/('wifi-native-'+a.action+'-'+nonce+'.private.log');log.write_text('\n'.join(evidence));log.chmod(0o600)
if __name__=='__main__':main()

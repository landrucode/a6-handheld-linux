#!/usr/bin/env python3
"""Boot the verified selected RAM bundle from user-prepared pwned DFU.
No reset, exploit or NAND operation. Default only validates local inputs.
"""
import argparse,json,subprocess,time,os,importlib.util
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--boot',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parents[1];os.umask(0o077);logdir=root/'build/session-logs';logdir.mkdir(parents=True,exist_ok=True);prefix='selected-ram-'+str(time.time_ns())+'-';irecovery=root/'.deps/legacy-ios-kit/bin/linux/x86_64/irecovery'
spec=importlib.util.spec_from_file_location('updater',root/'scripts/manage-a6-ram-update.py');updater=importlib.util.module_from_spec(spec);spec.loader.exec_module(updater)
selected=root/json.loads((root/'build/ram-updates/selection.json').read_text())['current'];release=updater.verify(selected)
if release['format']!=4:raise ValueError('Expected complete format-4 handheld bundle')
for path in (irecovery,root/'build/host/checkm8-bootkit-linux',*(root/'.deps/legacy-ios-kit/firmware'/name for name in ('iBSS.n42.RELEASE.patched','iBEC.n42.RELEASE.pwned.dfu','DeviceTree.n42ap.img3'))):
 if not path.is_file():raise ValueError('Required local boot component missing')
if not args.boot:
 print('Selected signed bundle and local boot inputs verified; no phone command sent');raise SystemExit(0)
def call(name,args):
 path=logdir/(prefix+name+'.private.log');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:subprocess.run([str(a) for a in args],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=40)
 print(name+' complete',flush=True)
def stage(name,mode,ibfl):
 for _ in range(20):
  result=subprocess.run([str(irecovery),'--query'],capture_output=True,text=True,timeout=5)
  if result.returncode==0 and 'MODE: '+mode in result.stdout and 'IBFL: '+ibfl in result.stdout:
   path=logdir/(prefix+name+'.private.log');path.write_text(result.stdout+result.stderr);path.chmod(0o600);print(name+' verified',flush=True);return
  time.sleep(.5)
 raise RuntimeError('Expected USB stage did not appear')
call('pwned-dfu-probe',[root/'build/host/checkm8-bootkit-linux','probe'])
call('ibss',[root/'build/host/checkm8-bootkit-linux','boot',root/'.deps/legacy-ios-kit/firmware/iBSS.n42.RELEASE.patched'])
stage('ibss-stage','DFU','0x1b')
call('ibec',[irecovery,'--file',root/'.deps/legacy-ios-kit/firmware/iBEC.n42.RELEASE.pwned.dfu'])
stage('ibec-stage','Recovery','0x1a')
call('tree',[irecovery,'--file',root/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.img3'])
call('tree-command',[irecovery,'--command','devicetree'])
call('image',[irecovery,'--file',selected/'a6-wifi.img3'])
call('bootx',[irecovery,'--command','bootx'])
print('Selected combined RAM candidate boot requested',flush=True)

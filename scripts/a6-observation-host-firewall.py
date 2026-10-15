#!/usr/bin/env python3
"""Allow the data-only observation endpoint from this phone, then remove the rule on expiry."""
import ipaddress,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'build/epiphany-ab/uplink-firewall.private.json'
def start_ticks(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    except OSError:return None

def main():
    if os.geteuid()!=0:raise SystemExit('Run this helper with sudo; it changes only the laptop observation rule.')
    info=CONFIG.lstat()
    if CONFIG.is_symlink() or info.st_uid!=ROOT.stat().st_uid or info.st_mode&0o077:raise ValueError('Private observation metadata ownership/mode differs')
    cfg=json.loads(CONFIG.read_text());peer=str(ipaddress.IPv4Address(cfg['peer']));host=str(ipaddress.IPv4Address(cfg['host']));port=int(cfg['port']);pid=int(cfg['pid']);expiry=int(cfg['expiry'])
    if not all(ipaddress.ip_address(x).is_private for x in (peer,host)) or not 1024<=port<=65535 or not re.fullmatch(r'[a-zA-Z0-9_-]+',cfg['interface']):raise ValueError('Invalid endpoint scope')
    if start_ticks(pid)!=cfg['start_ticks'] or not time.time()<expiry<=time.time()+8*3600:raise ValueError('Observation process expired')
    route=json.loads(subprocess.check_output(['ip','-j','route','get',peer]))[0]
    if route['prefsrc']!=host or route['dev']!=cfg['interface']:raise ValueError('LAN route changed')
    rule=['allow','in','on',cfg['interface'],'from',peer,'to',host,'port',str(port),'proto','tcp','comment','a6-data-observation']
    if len(sys.argv)==1:
        subprocess.run(['ufw',*rule],check=True)
        with (ROOT/'build/epiphany-ab/uplink-firewall-watch.private.log').open('a') as log:
            subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'watch'],stdout=log,stderr=log,start_new_session=True)
        print('Phone-only laptop observation rule installed; removes itself when observation ends.')
        return
    try:
        while time.time()<expiry and start_ticks(pid)==cfg['start_ticks']:time.sleep(5)
    finally:subprocess.run(['ufw','--force','delete',*rule],check=True)
if __name__=='__main__':main()

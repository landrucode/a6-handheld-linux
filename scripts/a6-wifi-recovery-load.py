#!/usr/bin/env python3
"""Bounded WLAN echo load without image storage; retain diagnostics before recovery."""
import argparse,hashlib,importlib.util,ipaddress,json,os,re,secrets,socket,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--mib',type=int,default=256);a.add_argument('--direction',choices=('echo','receive'),default='echo');args=a.parse_args()
    if not 1<=args.mib<=1024:a.error('mib must be 1..1024')
    os.umask(0o077);os.environ.pop('A6_USB_HTTP_RPC_TOKEN',None);os.environ['A6_ACM_BROKER']=str(ROOT/'build/wifi-native/acm.sock')
    spec=importlib.util.spec_from_file_location('connection',ROOT/'scripts/a6-wifi-connect.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);p=c.Phone()
    address=str(ipaddress.IPv4Address(re.search(r'(?m)^([0-9.]+)$',p.checked('cat /tmp/a6-connection.address'))[1]))
    route=json.loads(subprocess.check_output(['ip','-j','route','get',address]))[0];host=str(ipaddress.IPv4Address(route['prefsrc']))
    if route['dev']=='lo' or host.startswith('192.168.7.'):raise ValueError('Expected WLAN route')
    stem='/tmp/a6-load-'+secrets.token_hex(5);port=49154;handle=None
    path=ROOT/'build/session-logs'/('wifi-recovery-load-'+str(time.time_ns())+'.private.log')
    def snapshot(label):
        p.checked('echo '+label+'; cat /proc/uptime; cat /sys/firmware/a6_charger_policy/status; '
          +c.CLI+' -p/tmp/a6-connection.ctrl -iwlan0 status; '+c.IW+' dev wlan0 get power_save; '+c.IW+' dev wlan0 station dump; '
          'busybox ip neigh show dev wlan0; for field in rx_packets tx_packets rx_errors tx_errors rx_dropped tx_dropped; do '
          'printf "%s=" "$field"; cat /sys/class/net/wlan0/statistics/$field; done; '
          'busybox tail -n 45 /tmp/a6-power-longrun.log; busybox dmesg | busybox tail -n 50',timeout=20)
        p.checked('for counters in /sys/bus/usb/devices/*:*/a6_transport; do '
                  'test ! -r "$counters" || cat "$counters"; done',timeout=20)
    try:
        snapshot('LOAD_BEFORE')
        p.checked(c.NFT+' insert rule ip a6_guard input iifname "wlan0" ip saddr '+host+' ip daddr '+address+' tcp dport '+str(port)+' accept comment "'+stem[5:]+'"')
        out=p.checked(c.NFT+' -a list chain ip a6_guard input');handle=re.search(re.escape(stem[5:])+r'.*# handle (\d+)',out)[1]
        options=(' -u' if args.direction=='receive' else '')
        sink=(' OPEN:/dev/null' if args.direction=='receive' else ' EXEC:/bin/cat')
        p.checked("busybox setsid busybox timeout 600 "+c.SOCAT+options+' TCP4-LISTEN:'+str(port)+',bind='+address+',reuseaddr,fork'+sink+' </dev/null >'+stem+'.private.log 2>&1 & echo $! >'+stem+'.pid')
        payload=b'Q'*65536;started=time.monotonic();count=0
        deadline=time.monotonic()+10
        while True:
            try:peer=socket.create_connection((address,port),timeout=2);break
            except ConnectionRefusedError:
                if time.monotonic()>=deadline:raise
                time.sleep(.2)
        with peer as sock:
            sock.settimeout(10)
            for _ in range(args.mib*16):
                if time.monotonic()-started>600:raise TimeoutError('Load deadline')
                sock.sendall(payload);data=bytearray()
                if args.direction=='receive':
                    count+=len(payload)
                    if count%(16*1048576)==0:print('Sent '+str(count//1048576)+' MiB into phone without storage',flush=True)
                    continue
                while len(data)<len(payload):
                    chunk=sock.recv(len(payload)-len(data))
                    if not chunk:raise RuntimeError('Echo closed')
                    data.extend(chunk)
                if data!=payload:raise RuntimeError('Echo bytes differ')
                count+=len(data)
                if count%(16*1048576)==0:print('Verified '+str(count//1048576)+' MiB each direction',flush=True)
        snapshot('LOAD_AFTER');print('PASS '+str(args.mib)+' MiB direction='+args.direction+' in '+str(round(time.monotonic()-started,1))+'s',flush=True)
    except Exception:
        snapshot('LOAD_FAILURE_BEFORE_RECOVERY');raise
    finally:
        if handle is not None:p.serial(c.NFT+' delete rule ip a6_guard input handle '+handle+'; if test -s '+stem+'.pid; then read pid <'+stem+'.pid; kill -TERM -"$pid" 2>/dev/null; fi; true')
        path.write_text('\n'.join(p.evidence));path.chmod(0o600)
if __name__=='__main__':main()

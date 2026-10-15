#!/usr/bin/env python3
"""Bounded synthetic WLAN echo load; exact laptop-only firewall exception."""
import importlib.util,os,re,socket,time,hashlib,secrets,subprocess,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.environ.pop('A6_USB_HTTP_RPC_TOKEN',None);os.environ['A6_ACM_BROKER']=str(root/'build/wifi-native/acm.sock')
s=importlib.util.spec_from_file_location('c',root/'scripts/a6-wifi-connect.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c);p=c.Phone()
a=p.checked('cat /tmp/a6-connection.address');address=re.search(r'(?m)^([0-9.]+)$',a)[1];host=json.loads(subprocess.check_output(['ip','-j','route','get',address]))[0]['prefsrc']
log=root/'build/session-logs'/('wifi-echo-workload-'+str(int(time.time()))+'.private.log');fd=os.open(log,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
chain='workload_'+secrets.token_hex(4);stem='/tmp/a6-'+chain;port=49154
base=p.checked('cat /tmp/a6-connection.lease.events');leases=len(re.findall(r'(?m)^(?:bound|renew) [1-9][0-9]* [0-9]+$',base))
p.checked('kill -USR1 "$(cat /tmp/a6-connection.dhcp.pid)"')
p.checked(c.NFT+' add chain ip a6_guard '+chain+'; '+c.NFT+' insert rule ip a6_guard input jump '+chain)
p.checked('busybox setsid busybox timeout 650 '+c.SOCAT+' TCP4-LISTEN:'+str(port)+',bind='+address+',reuseaddr,fork EXEC:/bin/cat </dev/null >'+stem+'.log 2>&1 & echo $! >'+stem+'.pid; ('+'sleep 650; '+c.NFT+' flush chain ip a6_guard '+chain+') </dev/null >/dev/null 2>&1 &')
p.checked(c.NFT+' add rule ip a6_guard '+chain+' iifname \\"wlan0\\" ip saddr '+host+' ip daddr '+address+' tcp dport '+str(port)+' accept')
count=0;renewed=False;deadline=time.monotonic()+600;payload=b'Q'*65536
try:
 with os.fdopen(fd,'w',buffering=1) as f:
  while time.monotonic()<deadline:
   with socket.create_connection((address,port),timeout=5) as sock:
    sock.settimeout(5)
    for i in range(16):
     sock.sendall(payload);data=bytearray()
     while len(data)<len(payload):
      part=sock.recv(len(payload)-len(data))
      if not part:raise RuntimeError('Echo closed early')
      data.extend(part)
     if hashlib.sha256(data).digest()!=hashlib.sha256(payload).digest():raise RuntimeError('Echo corruption')
   command=c.CLI+' -p/tmp/a6-connection.ctrl -iwlan0 status; cat /tmp/a6-connection.lease.events; cat /sys/firmware/a6_charger_policy/status /sys/firmware/a6_charger_policy/low_battery_status; head -n 8 /proc/meminfo; busybox ping -I wlan0 -c 3 -W 2 "$(cat /tmp/a6-connection.gateway)" >/dev/null; echo PING_RC=$?'
   out=p.checked(command,timeout=15);f.write('HOST_TIME='+str(int(time.time()))+' ECHO_BYTES=1048576 VERIFIED=1\n'+out+'\n');p.evidence.clear()
   if not all(v in out for v in ['wpa_state=COMPLETED','PING_RC=0','auto=1 paused=0 fault=0','enabled=1']):raise RuntimeError('Connection/power failure')
   renewed|=len(re.findall(r'(?m)^(?:bound|renew) [1-9][0-9]* [0-9]+$',out))>leases
   count+=1
   if count==1:print('First verified one-MiB Wi-Fi transfer in each direction passed; gateway pings passed.',flush=True)
   time.sleep(min(10,max(0,deadline-time.monotonic())))
  if not renewed:raise RuntimeError('DHCP renewal not observed')
  f.write('SUMMARY_SAMPLES='+str(count)+' RENEWAL=1\n')
 print('Ten-minute Wi-Fi workload passed: '+str(count)+' verified MiB each direction; '+str(3*count)+' gateway pings; DHCP renewal confirmed.',flush=True)
finally:
 p.serial(c.NFT+' flush chain ip a6_guard '+chain+'; busybox kill -TERM -$(cat '+stem+'.pid) 2>/dev/null; true')

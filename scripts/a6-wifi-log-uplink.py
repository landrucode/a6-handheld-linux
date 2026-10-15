#!/usr/bin/env python3
"""Collect phone power/network records over a data-only TLS LAN endpoint for a bounded regression run."""
import argparse,hmac,http.server,importlib.util,ipaddress,json,os,re,secrets,ssl,subprocess,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes',type=int,default=60)
    args=parser.parse_args()
    if not 1<=args.minutes<=480:parser.error('minutes must be between 1 and 480')
    os.umask(0o077);os.environ['A6_ACM_BROKER']=str(ROOT/'build/wifi-native/acm.sock')
    spec=importlib.util.spec_from_file_location('connection',ROOT/'scripts/a6-wifi-connect.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);phone=c.Phone()
    address=str(ipaddress.IPv4Address(re.search(r'(?m)^([0-9.]+)$',phone.checked('cat /tmp/a6-connection.address'))[1]))
    route=json.loads(subprocess.check_output(['ip','-j','route','get',address]))[0];host=str(ipaddress.IPv4Address(route['prefsrc']))
    if not ipaddress.ip_address(host).is_private or host.startswith('192.168.7.'):raise ValueError('Expected LAN address')
    folder=ROOT/'build/session-logs'/('wifi-uplink-'+str(time.time_ns()));folder.mkdir(mode=0o700)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-subj','/CN=a6-observation','-addext','subjectAltName=IP:'+host,'-keyout',str(folder/'key.pem'),'-out',str(folder/'cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    token=secrets.token_hex(32);log=(folder/'battery.private.log').open('a',buffering=1);lock=threading.Lock();counts={'uploads':0}
    class Handler(http.server.BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(5)
        def log_message(self,*args):pass
        def do_POST(self):
            if self.path!='/battery' or self.client_address[0]!=address or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.send_error(403);return
            try:size=int(self.headers.get('Content-Length','0'))
            except ValueError:self.send_error(400);return
            if not 0<size<=32768:self.send_error(413);return
            data=self.rfile.read(size)
            if len(data)!=size or not data.startswith(b'A6_WIFI_LOG_UPLINK_V1\n'):
                self.send_error(400);return
            with lock:
                log.write('HOST_TIME='+str(int(time.time()))+'\n'+data.decode(errors='replace')+'\n');counts['uploads']+=1
            self.send_response(204);self.end_headers()
    class Server(http.server.ThreadingHTTPServer):
        daemon_threads=True
        def handle_error(self,*args):pass
    server=Server((host,0),Handler);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(folder/'cert.pem',folder/'key.pem');server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    meta=dict(peer=address,host=host,port=server.server_port,interface=route['dev'],pid=os.getpid(),start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],expiry=int(time.time()+args.minutes*60))
    (ROOT/'build/epiphany-ab/uplink-firewall.private.json').write_text(json.dumps(meta)+'\n')
    try:
        prefix='/tmp/graphics-runtime/tmp/a6-log-uplink'
        phone.upload((folder/'cert.pem').read_bytes(),prefix+'.pem')
        phone.upload(('Authorization: Bearer '+token+'\n').encode(),prefix+'.header',sensitive=True)
        phone.upload(('https://'+host+':'+str(server.server_port)+'/battery\n').encode(),prefix+'.url')
        phone.upload((ROOT/'rootfs/a6-wifi-log-uplink.sh').read_bytes(),'/tmp/a6-wifi-log-uplink.sh')
        phone.checked('busybox setsid busybox sh /tmp/a6-wifi-log-uplink.sh '+str(args.minutes*2)+' </dev/null >/tmp/a6-log-uplink.private.log 2>&1 & echo $! >/tmp/a6-log-uplink.pid')
        print(str(args.minutes)+'-minute data-only TLS observation started; root commands remain USB-only',flush=True)
        deadline=time.monotonic()+args.minutes*60;next_report=0
        while time.monotonic()<deadline:
            if counts['uploads']>next_report:
                print('Battery/network TLS uploads received: '+str(counts['uploads']),flush=True);next_report=counts['uploads']+29
            time.sleep(1)
        print('Observation finished; uploads='+str(counts['uploads']),flush=True)
    finally:
        server.shutdown();server.server_close();log.close()
        (folder/'setup.private.log').write_text('\n'.join(phone.evidence))
if __name__=='__main__':main()

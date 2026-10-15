#!/usr/bin/env python3
"""One headless PCM acquisition over ACM; private raw evidence only."""
import argparse,json,os,re,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--reader',type=Path,default=ROOT/'build/a6-capture-pcm-reader');args=p.parse_args()
out=args.output.resolve()
if not out.is_relative_to(ROOT/'build'):raise SystemExit('Capture evidence must stay under build/')
out.mkdir(parents=True,exist_ok=True)
os.environ['A6_ACM_BROKER']=str(ROOT/'build/wifi-native/acm.sock')
m=runpy.run_path(str(ROOT/'scripts/a6-provision-boot.py'));phone=m['module']('phone',ROOT/'scripts/a6-wifi-connect.py').Phone()
try:
 before=phone.checked("test -c /dev/snd/pcmC0D0c && busybox grep -q 'auto=1 paused=0 fault=0' /sys/firmware/a6_charger_policy/status && busybox grep -q 'enabled=1 .*triggered=0' /sys/firmware/a6_charger_policy/low_battery_status && cat /sys/firmware/a6_alsa_status")
 (out/'before.private.log').write_text(before)
 phone.upload(args.reader.read_bytes(),'/tmp/a6-capture-pcm-reader')
 result=phone.checked("busybox chmod 700 /tmp/a6-capture-pcm-reader && busybox timeout 8 /tmp/a6-capture-pcm-reader; pcm_rc=$?; printf 'PCM_RC=%s\\n' \"$pcm_rc\"; cat /sys/firmware/a6_alsa_status; cat /sys/firmware/a6_charger_policy/status; cat /sys/firmware/a6_charger_policy/low_battery_status",timeout=30)
 (out/'result.private.log').write_text(result)
 values={k:int(v) for k,v in re.findall(r'^(stage|error|frames|left_nonzero|right_nonzero|left_peak|right_peak|elapsed_ms|drop_error|close_error|PCM_RC)=(\d+)$',result,re.M)}
 (out/'analysis.private.json').write_text(json.dumps(values,indent=2)+'\n');print(json.dumps(values))
 if values.get('PCM_RC')!=0 or values.get('frames')!=44100:raise SystemExit('PCM acquisition incomplete; private evidence retained')
 if not re.search(r'capture .*cleanup=0',result):raise SystemExit('Inspect exact restore status in private result log')
finally:
 (out/'serial.private.log').write_text('\n'.join(phone.evidence))

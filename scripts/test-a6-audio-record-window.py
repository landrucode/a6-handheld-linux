#!/usr/bin/env python3
"""Execute actual record branch with delayed data, reused files, and frontend failures."""
from pathlib import Path
import os,subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'rootfs/a6-audio-session.sh').read_text();a=s.index(' record)\n')+len(' record)\n');b=s.index('  ;;\n *)',a)
branch=s[a:b]
with tempfile.TemporaryDirectory() as d:
 d=Path(d);bin=d/'bin';bin.mkdir()
 (bin/'pw-record').write_text('''#!/usr/bin/env python3
import os,sys,time,signal
signal.signal(signal.SIGINT,lambda *args: sys.exit(1))
path=sys.argv[-1]
with open(path,'wb') as f:
 f.write(b'0'*44);f.flush()
 time.sleep(.15)
 if os.environ.get('FAIL')=='before':sys.exit(42)
 f.write(b'pcm'*1024);f.flush()
 if os.environ.get('FAIL')=='after':sys.exit(42)
 while True:time.sleep(.01)
''');(bin/'pw-record').chmod(0o755)
 (bin/'pw-cli').write_text('''#!/bin/sh
if test "$1" = ls; then
 printf 'id 31, type Node\n node.name = "a6-microphone"\n'
else
 test "${FAIL:-}" != command || exit 7
 test "$1" = send-command && test "$2" = 31 && test "$3" = Suspend && test "$4" = '{}' || exit 2
 echo MIC_SUSPENDED
fi
''');(bin/'pw-cli').chmod(0o755)
 script=d/'record';script.write_text('''#!/bin/bash
set -euo pipefail
sleep(){ if [[ $1 == 5 ]]; then /usr/bin/sleep .05; else /usr/bin/sleep .01; fi; }
set -- record "$1"
'''+branch);script.chmod(0o755)
 env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH'])
 wav=d/'voice.wav';wav.write_bytes(b'old'*2000)
 result=subprocess.run([str(script),str(wav)],env=env,capture_output=True,text=True,timeout=5)
 assert result.returncode==0 and 'A6_PIPEWIRE_RECORD_STARTED' in result.stdout and 'MIC_SUSPENDED' in result.stdout,result
 assert wav.stat().st_size==44+3072
 for fail in ('before','after','command'):
  result=subprocess.run([str(script),str(wav)],env=dict(env,FAIL=fail),capture_output=True,text=True,timeout=5)
  assert result.returncode and 'MIC_SUSPENDED' not in result.stdout,result
print('PASS: actual recorder waits for fresh data, handles controlled SIGINT, suspends the correct node and rejects frontend failures')

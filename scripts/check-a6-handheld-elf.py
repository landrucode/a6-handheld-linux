#!/usr/bin/env python3
"""Check locally built ARM image startup on the host; no phone or performance claim."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop-image',type=Path,required=True)
    parser.add_argument('--browser-image',type=Path)
    args = parser.parse_args()
    qemu = shutil.which('qemu-arm-static') or shutil.which('qemu-arm')
    if not qemu: raise ValueError('Host ARM user emulator required')
    images = [args.desktop_image] + ([args.browser_image] if args.browser_image else [])
    for image in images:
        if not image.resolve().is_relative_to(ROOT/'build'):
            raise ValueError('Use generated images under build/')
    tools = ROOT/'.deps/squashfs-tools-4.7.2/squashfs-tools'
    report_dir = ROOT/'build/handheld-elf-check'
    report_dir.mkdir(parents=True,exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='arm-image-check-') as temporary:
        stage = Path(temporary)
        for name,image in zip(('desktop','browser'),images):
            subprocess.run([str(tools/'unsquashfs'),'-no-progress','-processors','2',
                            '-d',str(stage/name),str(image.resolve())],check=True,stdout=subprocess.DEVNULL)
        root = stage/'desktop/graphics-runtime'
        home = stage/'home';home.mkdir()
        # Startup creates the phone's user; emulate account lookup only in the
        # extracted QA trees so ssh -V can run before a real boot's prepare step.
        for tree in [root] + ([stage/'browser'] if args.browser_image else []):
            (tree/'etc').mkdir(exist_ok=True)
            passwd = tree/'etc/passwd'
            contents = passwd.read_text() if passwd.exists() else ''
            if not any(line.split(':')[2:3] == [str(os.getuid())] for line in contents.splitlines()):
                passwd.write_text(contents+'\na6-qa:x:'+str(os.getuid())+':'+str(os.getgid())+':ELF check:'+str(home)+':/bin/bash\n')
        checks = [('bash',root,'bin/bash',['--version'],[]),
                  ('foot',root,'usr/bin/foot',['--version'],[]),
                  ('keyboard',root,'usr/local/bin/wvkbd-native',['--help'],[]),
                  ('labwc',root,'opt/a6/labwc-runtime/usr/bin/labwc',['--version'],['opt/a6/labwc-runtime/usr/lib']),
                  ('panel-libraries',root,'usr/local/bin/a6-labwc-panel',[],[]),
                  ('mpv',root,'opt/a6/media-runtime/usr/bin/mpv',['--version'],['opt/a6/media-runtime/usr/lib']),
                  ('pipewire',root,'opt/a6/audio-runtime/usr/bin/pipewire',['--version'],['opt/a6/audio-runtime/usr/lib']),
                  ('ssh',root,'usr/bin/ssh',['-V'],[]),
                  ('ip',root,'usr/bin/ip',['-V'],[]),
                  ('htop',root,'usr/bin/htop',['--version'],[]),
                  ('tmux',root,'usr/bin/tmux',['-V'],[])]
        if args.browser_image:
            browser = stage/'browser'
            checks += [('epiphany',browser,'usr/bin/epiphany',['--version'],[]),
                       ('bubblewrap',browser,'usr/bin/bwrap',['--version'],[])]
        checks += [('decode-fixture',root,'opt/a6/media-runtime/usr/bin/mpv',
                    ['--no-config','--vo=null','--no-audio','--frames=10',
                     str(root/'usr/local/share/a6/video-360p.mp4')],['opt/a6/media-runtime/usr/lib'])]
        for name,tree,relative,arguments,libraries in checks:
            paths = ':'.join(str(tree/path) for path in [*libraries,'usr/lib','lib'])
            command = [qemu,'-cpu','cortex-a15','-L',str(tree),'-E','LC_ALL=C',
                       '-E','HOME='+str(home),'-E','LD_BIND_NOW=1',
                       str(tree/'usr/lib/ld-linux-armhf.so.3'),'--library-path',paths]
            if name == 'panel-libraries': command += ['--list']
            command += [str(tree/relative),*arguments]
            try:
                result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
                output,rc = result.stdout,result.returncode
            except subprocess.TimeoutExpired as error:
                output,rc = error.stdout or b'','timeout'
            (report_dir/(name+'.private.log')).write_bytes(output)
            results.append(dict(name=name,returncode=rc));print(name+': '+str(rc),flush=True)
    (report_dir/'results.json').write_text(json.dumps(dict(checks=results,
        qemu_version=subprocess.check_output([qemu,'--version'],text=True).splitlines()[0],
        hardware_or_performance_test=False),indent=2)+'\n')
    if any(item['returncode'] != 0 for item in results): raise SystemExit(1)

if __name__ == '__main__': main()

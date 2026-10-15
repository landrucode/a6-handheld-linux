#!/usr/bin/env python3
"""Cross-build pinned upstream PSI oomd and jsoncpp, without systemd plugins."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import json

ROOT=Path(__file__).resolve().parents[1]
SOURCES={'oomd':'f8e553ba290b9ac9165a634688ccf82660d5c7e1','jsoncpp':'89e2973c754a9c02a49974d839779b151e95afd6'}
stage=ROOT/'build/oomd';stage.mkdir(parents=True,exist_ok=True)
sysroot=ROOT/'build/aquamarine-sysroot'
for name,revision in SOURCES.items():
    if subprocess.check_output(['git','-C',str(ROOT/'.deps'/name),'rev-parse','HEAD'],text=True).strip()!=revision:
        raise ValueError('Unexpected '+name+' revision')
(stage/'Version.h').write_text('#pragma once\n#define GIT_VERSION "'+SOURCES['oomd']+'"\n')
flags=['clang++','--target=arm-linux-gnueabihf','--sysroot='+str(sysroot),
       '--gcc-install-dir='+str(sysroot/'usr/lib/gcc/armv7l-unknown-linux-gnueabihf/16.1.1'),
       '-march=armv7-a','-mfpu=neon','-mfloat-abi=hard','-std=c++20','-O2','-fPIE',
       '-fstack-protector-strong','-D_FORTIFY_SOURCE=2','-D_TIME_BITS=64','-D_FILE_OFFSET_BITS=64','-DMESON_BUILD',
       '-ffile-prefix-map='+str(ROOT)+'=.', '-fdebug-prefix-map='+str(ROOT)+'=.',
       '-I'+str(ROOT/'.deps/oomd/src'),'-I'+str(ROOT/'.deps/jsoncpp/include'),'-I'+str(stage)]
# Use the exact upstream public source set from Meson; no custom policy code.
meson=(ROOT/'.deps/oomd/meson.build').read_text()
source_names=meson.split("srcs = files('''",1)[1].split("'''.split())",1)[0].split()
sources=[ROOT/'.deps/oomd'/s for s in source_names]+[ROOT/'.deps/oomd/src/oomd/Main.cpp']
sources += list((ROOT/'.deps/jsoncpp/src/lib_json').glob('*.cpp'))
def compile_source(src):
    obj=stage/(str(src.relative_to(ROOT/'.deps')).replace('/','_')+'.o')
    subprocess.run(flags+['-c',str(src),'-o',str(obj)],check=True)
    return obj
with ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(compile_source,sources))
subprocess.run(flags+['-fuse-ld=lld',*[str(p) for p in objects],'-pthread','-pie','-Wl,-z,relro,-z,now','-o',str(stage/'oomd')],check=True)
subprocess.run(['llvm-strip','--strip-debug',str(stage/'oomd')],check=True)
(stage/'sources.json').write_text(json.dumps({'upstream':SOURCES,'license':'oomd GPL-2.0; jsoncpp MIT','systemd_plugins':False},indent=2)+'\n')
print('Pinned upstream PSI oomd built')

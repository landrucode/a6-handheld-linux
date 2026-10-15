#!/usr/bin/env python3
"""Prepare signature-verified mpv, yt-dlp and their ARM runtime closure."""
import importlib.util
import argparse,hashlib,json,posixpath,re,shutil,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
stage=ROOT/'build/media-runtime';stage.mkdir(exist_ok=True)
runtime=stage/'runtime';runtime.mkdir(exist_ok=True)
spec_path=ROOT/'rootfs/arch-media-packages.json'
if spec_path.exists():
 pinned_spec=json.loads(spec_path.read_text())
 packages={name:{'FILENAME':[meta['filename']], 'SHA256SUM':[meta['sha256']],
                 'repo':meta['repo'], 'PROVIDES':meta.get('provides',[]),
                 'DEPENDS':meta.get('dependencies',[]),'LICENSE':meta.get('license',[]),'URL':meta.get('upstream',[])}
           for name,meta in pinned_spec['packages'].items()}
else:
 packages=json.loads((ROOT/'build/labwc/repo-packages.json').read_text())
# A clean labwc base lacks libraries inherited from the old Hyprland root.
# Resolve those only from other checked-in package locks, never a rolling DB.
for lock in ('arch-browser-packages.json', 'arch-aquamarine-build-packages.json'):
 for name,meta in json.loads((ROOT/'rootfs'/lock).read_text())['packages'].items():
  if name not in packages:
   packages[name]={'FILENAME':[meta['filename']], 'SHA256SUM':[meta['sha256']],
                   'repo':meta['repo'], 'PROVIDES':meta.get('provides',[]),
                   'DEPENDS':meta.get('dependencies',[]),'LICENSE':meta.get('license',[]),
                   'URL':meta.get('upstream',[])}
providers={'libSPIRV-Tools-opt.so':'spirv-tools','libSPIRV-Tools.so':'spirv-tools','libSPIRV-Tools-link.so':'spirv-tools','libdecor-0.so.0':'libdecor','libcdio_paranoia.so.2':'libcdio-paranoia','libcdio_cdda.so.2':'libcdio-paranoia','libvapoursynth-script.so.0':'vapoursynth','libluajit-5.1.so.2':'luajit','libSDL2-2.0.so.0':'sdl2','libuchardet.so.0':'uchardet','libgsm.so.1':'gsm','libopenjp2.so.7':'openjpeg2','libtheoraenc.so.2':'libtheora','libtheoradec.so.2':'libtheora','libtheora.so.0':'libtheora','libv4l2.so.0':'v4l-utils','libv4lconvert.so.0':'v4l-utils','libOpenCL.so.1':'ocl-icd','libpgm-5.3.so.0':'libpgm','libmpdec.so.4':'mpdecimal','libfftw3_threads.so.3':'fftw','libfftw3f_threads.so.3':'fftw','libx264.so.165':'x264','libx265.so.216':'x265','libaom.so.3':'aom','libdav1d.so.7':'dav1d','librav1e.so.0.8':'rav1e','libSvtAv1Enc.so.4':'svt-av1'}
for name,f in packages.items():
 for p in f.get('PROVIDES',[]):
  m=re.fullmatch(r'(.+\.so)=([0-9.]+)-32',p)
  if m:providers[m[1]+'.'+m[2]]=name
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--desktop-base',type=Path,default=ROOT/'build/arch-bootstrap/arch-hyprland-user-desktop-audio-verified.squashfs')
args=parser.parse_args()
base_spec=importlib.util.spec_from_file_location('base',ROOT/'scripts/a6-desktop-base.py')
base_module=importlib.util.module_from_spec(base_spec);base_spec.loader.exec_module(base_module)
base_sha=base_module.verified_base(args.desktop_base,ROOT)
base_dir=stage/('base-'+base_sha)
if not base_dir.exists():
 subprocess.run([str(ROOT/'.deps/squashfs-tools-4.7.2/squashfs-tools/unsquashfs'),'-no-progress','-processors','2','-d',str(base_dir),str(args.desktop_base),'graphics-runtime/usr/lib'],check=True,stdout=subprocess.DEVNULL)
base=base_dir/'graphics-runtime/usr/lib'
manifest={}
if spec_path.exists(): pinned=json.loads(spec_path.read_text())['packages']
else:pinned={}
signer='68B3537F39A313B3E574D06777193F152BDBE6A6'
mirror='https://ca.us.mirror.archlinuxarm.org/armv7h/'
def install(name):
 if name not in packages:
  requested=name
  name=next((n for n,f in packages.items() if any(re.split('[<>=]',p)[0]==requested for p in f.get('PROVIDES',[]))),None)
  if name is None:raise ValueError('Media dependency absent from checked-in locks: '+requested)
 if name in manifest:return
 f=packages[name];meta=pinned.get(name,{'filename':f['FILENAME'][0],'sha256':f['SHA256SUM'][0],'repo':f['repo']})
 p=stage/meta['filename']
 for suffix in ('','.sig'):
  target=Path(str(p)+suffix)
  cached=ROOT/'build/arch-bootstrap/downloads'/(meta['filename']+suffix)
  if not target.exists() and cached.is_file():shutil.copyfile(cached,target)
  if not target.exists():
   tmp=Path(str(target)+'.part');subprocess.run(['curl','-fsSL','--max-time','120',mirror+meta['repo']+'/'+meta['filename']+suffix,'-o',str(tmp)],check=True);tmp.replace(target)
 if hashlib.file_digest(p.open('rb'),'sha256').hexdigest()!=meta['sha256']:raise ValueError('Package hash differs: '+name)
 r=subprocess.run(['gpg','--homedir',str(ROOT/'build/arch-bootstrap/gnupg'),'--batch','--status-fd','1','--verify',str(p)+'.sig',str(p)],capture_output=True,text=True,check=True)
 if '[GNUPG:] VALIDSIG '+signer+' ' not in r.stdout:raise ValueError('Package signer differs: '+name)
 with tarfile.open(p) as t:
  for member in t:
   if '/lib-dynload/_tkinter.' in member.name:continue
   if member.name.startswith('usr/bin/') and Path(member.name).name not in ('mpv','yt-dlp','swaybg','python','python3','python3.14','ffmpeg','ffprobe'):continue
   if not member.name.startswith(('usr/bin/','usr/lib/','usr/share/mpv/','usr/share/yt-dlp/')):continue
   if member.name.startswith(('usr/lib/pkgconfig/','usr/lib/cmake/')) or member.name.endswith('.a'):continue
   if member.issym() and member.linkname.startswith('/'):
    member=member.replace(linkname=posixpath.relpath(member.linkname.lstrip('/'),posixpath.dirname(member.name)))
   t.extract(member,runtime,filter='data')
 meta.update(provides=f.get('PROVIDES',[]),dependencies=f.get('DEPENDS',[]),license=f.get('LICENSE',[]),upstream=f.get('URL',[]))
 manifest[name]=meta
 print('Verified media package:',name,flush=True)
 if name.startswith('python-') or name=='yt-dlp':
  for dep in f.get('DEPENDS',[]):
   dep=re.split('[<>=]',dep)[0]
   if dep.startswith('python-'):install(dep)
for name,fields in packages.items():
 if name in pinned or (stage/fields['FILENAME'][0]).exists():install(name)
for name in ('mpv','yt-dlp','python','swaybg','sdl3'):install(name)
for path in (runtime/'usr/bin').iterdir():
 if path.name not in ('mpv','yt-dlp','swaybg','python','python3','python3.14','ffmpeg','ffprobe'):path.unlink()
for path in (runtime/'usr/lib').rglob('_tkinter.*.so'):path.unlink()
absolute_libraries=set()
seen=set()
while True:
 queue=[p for p in (runtime/'usr').rglob('*') if p.is_file() and not p.is_symlink() and p not in seen]
 if not queue:break
 for obj in queue:
  seen.add(obj)
  with obj.open('rb') as f:
   if f.read(4)!=b'\x7fELF':continue
  dynamic=subprocess.check_output(['llvm-readelf','-d',str(obj)],text=True,stderr=subprocess.DEVNULL)
  for soname in re.findall(r'Shared library: \[([^]]+)\]',dynamic):
   if soname.startswith('/'):
    if not soname.startswith('/usr/lib/') or '/' in soname[9:]:raise ValueError('Unexpected absolute media dependency')
    absolute_libraries.add(Path(soname).name);soname=Path(soname).name
   dest=runtime/'usr/lib'/soname
   if dest.exists() or (obj.parent/soname).exists():continue
   nested=next((p for p in (runtime/'usr/lib').rglob(soname) if p.exists()),None)
   if nested is not None:shutil.copy2(nested.resolve(),dest)
   elif (base/soname).exists():
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2((base/soname).resolve(),dest)
   elif soname in providers:install(providers[soname])
   elif soname.startswith('libxcb-'):install('libxcb')
   elif soname.split('.so')[0] in packages:install(soname.split('.so')[0])
   elif soname.split('.so')[0].lower() in packages:install(soname.split('.so')[0].lower())
   elif soname.split('.so')[0].lower().removeprefix('lib') in packages:install(soname.split('.so')[0].lower().removeprefix('lib'))
   else:raise ValueError('Unresolved media library: '+soname)
for p in runtime.rglob('*'):
 if not p.is_symlink():p.chmod(0o755 if p.is_dir() or p.stat().st_mode&0o111 else 0o644)
(stage/'manifest.json').write_text(json.dumps({'mirror':mirror,'signing_fingerprint':signer,'packages':manifest,'absolute_libraries':sorted(absolute_libraries),'desktop_base_sha256':base_sha},indent=2)+'\n')
print('Signed mpv/yt-dlp runtime closure prepared')

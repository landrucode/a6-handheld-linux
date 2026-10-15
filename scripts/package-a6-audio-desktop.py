#!/usr/bin/env python3
"""Add the tested audio runtime to the accepted RAM desktop; retain the base."""
import argparse, hashlib, json, shutil, subprocess, tarfile, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='a0c99e064092da1943c11b14f31686c9283b2ff8f6be28e78ec8e400f12cba22'
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--runtime',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args()
 source=ROOT/'build/arch-bootstrap/arch-hyprland-user-desktop-accepted-launchfix.squashfs';out=v.output.resolve();runtime=v.runtime.resolve()
 if not all(p.is_relative_to(ROOT/'build') for p in (out,runtime)) or out.exists() or digest(source)!=BASE:raise ValueError('Expected accepted base and new ignored output')
 tools=ROOT/'.deps/squashfs-tools-4.7.2/squashfs-tools'
 if subprocess.check_output(['git','-C',str(tools.parent),'rev-parse','HEAD'],text=True).strip()!='99d23a31b471433c51e9c145aeba2ab1536e34df':raise ValueError('Unexpected SquashFS tools revision')
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(dir=out.parent,prefix='audio-package-') as tmp:
  stage=Path(tmp)/'root'
  subprocess.run([str(tools/'unsquashfs'),'-no-progress','-processors','2','-d',str(stage),str(source)],check=True,stdout=subprocess.DEVNULL)
  unchanged={str(p.relative_to(stage)):digest(p) for p in stage.rglob('*') if p.is_file() and not p.is_symlink() and str(p.relative_to(stage))!='graphics-runtime/usr/local/bin/a6-audio-session'}
  audio=stage/'graphics-runtime/opt/a6/audio-runtime';audio.mkdir(parents=True)
  unpack=Path(tmp)/'audio'
  with tarfile.open(runtime) as t:
   members=[m for m in t.getmembers() if m.name=='runtime' or m.name.startswith('runtime/')]
   t.extractall(unpack,members=members,filter='data')
  shutil.copytree(unpack/'runtime',audio,dirs_exist_ok=True,symlinks=True)
  launcher=stage/'graphics-runtime/usr/local/bin/a6-audio-session'
  shutil.copyfile(ROOT/'rootfs/a6-audio-session.sh',launcher);launcher.chmod(0o755)
  shutil.copyfile(launcher,audio/'usr/local/bin/a6-audio-session')
  for p in audio.rglob('*'):
   if not p.is_symlink():p.chmod((p.stat().st_mode&0o777)|0o444|(0o111 if p.is_dir() else 0))
  expected={str(p.relative_to(stage)):digest(p) for p in audio.rglob('*') if p.is_file() and not p.is_symlink()};expected[str(launcher.relative_to(stage))]=digest(launcher)
  subprocess.run([str(tools/'mksquashfs'),str(stage),str(out),'-noappend','-all-root','-root-mode','0755','-no-xattrs','-comp','zstd','-Xcompression-level','15','-b','131072','-repro-time','0','-processors','2','-mem','256M','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  verified=Path(tmp)/'verified'
  subprocess.run([str(tools/'unsquashfs'),'-no-progress','-processors','2','-d',str(verified),str(out)],check=True,stdout=subprocess.DEVNULL)
  for name,h in (unchanged|expected).items():
   if digest(verified/name)!=h:raise ValueError('Audio round-trip mismatch: '+name)
 out.with_suffix('.json').write_text(json.dumps(dict(base_sha256=BASE,sha256=digest(out),bytes=out.stat().st_size,audio_files=len(expected),unchanged_desktop_files=len(unchanged),cold_boot_tested=False),indent=2)+'\n')
 print('Audio desktop packaged and round-trip verified',flush=True)
if __name__=='__main__':main()

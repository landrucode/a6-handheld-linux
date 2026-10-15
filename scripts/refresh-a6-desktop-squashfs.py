#!/usr/bin/env python3
"""Apply public desktop fixes to the pinned RAM base, leaving the source intact."""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS_COMMIT = '99d23a31b471433c51e9c145aeba2ab1536e34df'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compositor', choices=('hyprland','labwc'), default='labwc')
    parser.add_argument('--reuse-components', action='store_true', help='Packaging-only refresh using components already built in this session')
    args = parser.parse_args()
    def build_component(*arguments, **options):
        if not args.reuse_components:
            subprocess.run(*arguments, **options)
    source, output = args.source.resolve(), args.output.resolve()
    if not source.is_relative_to(ROOT/'build') or not output.is_relative_to(ROOT/'build'):
        raise ValueError('RAM artifacts must remain under ignored build/')
    spec = importlib.util.spec_from_file_location('base', ROOT/'scripts/a6-desktop-base.py')
    base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
    base_sha = base.verified_base(source, ROOT)
    if output.exists():
        raise ValueError('Use a new output path')
    tools = ROOT/'.deps/squashfs-tools-4.7.2'
    if subprocess.check_output(['git','-C',str(tools),'rev-parse','HEAD'],text=True).strip() != TOOLS_COMMIT:
        raise ValueError('Unexpected SquashFS tools revision')
    replacements = {
        'usr/local/share/a6/local-video.mp4': ROOT/'build/local-media/local-video.mp4',
        'usr/local/share/a6/touch-workload.html': ROOT/'rootfs/desktop/touch-workload.html',
        'usr/local/share/a6/touch-calibration.matrix': ROOT/'rootfs/a6-touch-calibration.matrix',
        'etc/udev/rules.d/99-a6-touch-calibration.rules': ROOT/'rootfs/99-a6-touch-calibration.rules',
        'usr/local/bin/a6-user-tools-check': ROOT/'rootfs/a6-user-tools-check.sh',
        'usr/local/bin/wvkbd-native': ROOT/'build/arm/wvkbd-native',
        'usr/local/bin/oomd': ROOT/'build/oomd/oomd',
        'usr/local/bin/a6-app-panel': ROOT/'build/app-panel/a6-app-panel',
        'usr/local/bin/a6-focus-app.sh': ROOT/'rootfs/a6-focus-app.sh',
        'usr/local/bin/a6-start-desktop-panel': ROOT/'rootfs/a6-start-desktop-panel.sh',
        'usr/local/share/a6/browser-oomd.json': ROOT/'rootfs/a6-browser-oomd.json',
        'usr/local/share/a6/hyprland.lua': ROOT/'rootfs/a6-hyprland.lua',
    }
    for name in ('palette.sh', 'foot.ini', 'wvkbd.args'):
        replacements['usr/local/share/a6/theme/'+name] = ROOT/'desktop/theme'/name
    for name in ('a6-start-desktop','a6-prepare-user-desktop','a6-label-native-touch',
                 'a6-start-user-hyprland','a6-start-native-keyboard'):
        replacements['usr/local/bin/'+name] = ROOT/'rootfs'/(name+'.sh')
    import os
    env = dict(os.environ, A6_WVKBD_PROFILE='native', A6_WVKBD_POLL_CANDIDATE='1')
    build_component(['bash',str(ROOT/'scripts/build-a6-wvkbd.sh')],check=True,env=env,
                   stdout=subprocess.DEVNULL)
    build_component(['python3',str(ROOT/'scripts/build-a6-oomd.py')],check=True)
    build_component(['bash',str(ROOT/'scripts/build-a6-app-panel.sh')],check=True)
    build_component(['bash',str(ROOT/'scripts/build-a6-local-video.sh')],check=True)
    build_component(['python3',str(ROOT/'scripts/prepare-a6-desktop-tools.py')],check=True)
    build_component(['python3',str(ROOT/'scripts/prepare-a6-user-tools.py')],check=True)
    if args.compositor == 'labwc':
        build_component(['bash',str(ROOT/'scripts/build-a6-labwc-panel.sh')],check=True)
        build_component(['python3',str(ROOT/'scripts/prepare-a6-media-runtime.py'),'--desktop-base',str(source)],check=True)
        replacements['usr/local/bin/a6-launch-video'] = ROOT/'rootfs/a6-launch-video.sh'
        replacements['usr/local/bin/yt-dlp'] = ROOT/'rootfs/a6-yt-dlp.sh'
        replacements['usr/local/bin/a6-video-workload'] = ROOT/'rootfs/a6-video-workload.sh'
        replacements['usr/local/share/a6/video-measure.lua'] = ROOT/'rootfs/desktop/video-measure.lua'
        for height in (360,480):
            replacements[f'usr/local/share/a6/video-{height}p.mp4'] = ROOT/f'build/local-media/video-{height}p.mp4'
        replacements['usr/local/bin/a6-labwc-panel'] = ROOT/'build/app-panel/a6-labwc-panel'
        replacements['usr/local/bin/a6-start-user-labwc'] = ROOT/'rootfs/a6-start-user-labwc.sh'
        for name in ('rc.xml','autostart'):
            replacements['usr/local/share/a6/labwc/'+name] = ROOT/'rootfs/labwc'/name
    # Generate compositor colours directly from the public shell palette.
    if args.compositor == 'labwc':
        import re
        palette = dict(re.findall(r'^(A6_\w+)=([0-9a-f]{6})',
                                  (ROOT/'desktop/theme/palette.sh').read_text(), re.M))
        theme = ROOT/'build/labwc/themerc-override'
        theme.write_text('border.width: 2\n' + ''.join(
            key+': #'+palette[value]+'\n' for key,value in (
                ('window.active.border.color','A6_LAVENDER'),
                ('window.inactive.border.color','A6_SURFACE'),
                ('window.active.title.bg.color','A6_BG_ALT'),
                ('window.inactive.title.bg.color','A6_BG'),
                ('window.active.label.text.color','A6_FG'),
                ('window.inactive.label.text.color','A6_FG_DIM'),
                ('osd.bg.color','A6_BG_ALT'),('osd.label.text.color','A6_FG'))))
        replacements['usr/local/share/a6/labwc/themerc-override'] = theme
        replacements['usr/share/themes/A6 Pastel/labwc/themerc'] = theme
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='a6-desktop-refresh-',dir=output.parent) as temporary:
        unpacked = Path(temporary)/'source'
        subprocess.run([str(tools/'squashfs-tools/unsquashfs'),'-no-progress','-processors','2',
                        '-d',str(unpacked),str(source)],check=True,stdout=subprocess.DEVNULL)
        root = unpacked/'graphics-runtime'
        for relative in ('','home','run','run/user'):
            path = root/relative
            path.mkdir(parents=True,exist_ok=True)
            path.chmod(0o755)
        (root/'opt/a6/touch-offset.so').unlink(missing_ok=True)
        desktop_tools = ROOT/'build/desktop-tools/runtime/usr'
        for original in desktop_tools.rglob('*'):
            destination = root/'usr'/original.relative_to(desktop_tools)
            if original.is_symlink() or destination.is_symlink():
                destination.unlink(missing_ok=True)
        shutil.copytree(desktop_tools,root/'usr',dirs_exist_ok=True,symlinks=True)
        expected = {}
        user_tools = ROOT/'build/user-tools/runtime/usr'
        for original in user_tools.rglob('*'):
            relative = original.relative_to(user_tools)
            destination = root/'usr'/relative
            if original.is_symlink():
                destination.unlink(missing_ok=True)
                destination.symlink_to(original.readlink())
            elif original.is_dir():
                destination.mkdir(parents=True,exist_ok=True)
            else:
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.unlink(missing_ok=True)
                shutil.copy2(original,destination)
                expected['usr/'+str(relative)] = digest(original)
        (root/'etc/ssl').mkdir(parents=True,exist_ok=True)
        for name in ('sudo','su','doas','sshd'):
            for directory in ('usr/bin','bin','usr/sbin','sbin'):
                (root/directory/name).unlink(missing_ok=True)

        if args.compositor == 'labwc':
            media = ROOT/'build/media-runtime/runtime/usr'
            (root/'opt/a6/media-runtime').mkdir(parents=True,exist_ok=True)
            (root/'opt/a6/media-runtime').chmod(0o755)
            shutil.copytree(media,root/'opt/a6/media-runtime/usr',dirs_exist_ok=True,symlinks=True)
            for original in media.rglob('*'):
                if original.is_file() and not original.is_symlink():
                    expected['opt/a6/media-runtime/usr/'+str(original.relative_to(media))] = digest(original)
            media_manifest = ROOT/'build/media-runtime/manifest.json'
            if not media_manifest.exists(): media_manifest = ROOT/'rootfs/arch-media-packages.json'
            for soname in json.loads(media_manifest.read_text()).get('absolute_libraries',[]):
                replacements['usr/lib/'+soname]=media/'lib'/soname
            runtime = ROOT/'build/labwc/runtime/usr'
            # The clean base does not inherit GTK/icon libraries from Hyprland.
            closure_spec = importlib.util.spec_from_file_location('closure',ROOT/'scripts/a6-runtime-libraries.py')
            closure = importlib.util.module_from_spec(closure_spec); closure_spec.loader.exec_module(closure)
            closure.complete(runtime,root/'usr/lib',[ROOT/'build/aquamarine-sysroot/usr/lib',media/'lib'],ROOT/'build')
            shutil.copy2(media/'bin/swaybg',runtime/'bin/swaybg')
            (root/'opt/a6/labwc-runtime').mkdir(parents=True,exist_ok=True)
            (root/'opt/a6/labwc-runtime').chmod(0o755)
            shutil.copytree(runtime,root/'opt/a6/labwc-runtime/usr',dirs_exist_ok=True,symlinks=True)
            for original in runtime.rglob('*'):
                if original.is_file() and not original.is_symlink():
                    expected['opt/a6/labwc-runtime/usr/'+str(original.relative_to(runtime))] = digest(original)
            for relative in ('lib/glycin-loaders','share/glycin-loaders','share/mime'):
                shutil.copytree(runtime/relative,root/'usr'/relative,dirs_exist_ok=True,symlinks=True)
                for original in (runtime/relative).rglob('*'):
                    if original.is_file() and not original.is_symlink():
                        expected['usr/'+str(original.relative_to(runtime))] = digest(original)
            replacements['usr/bin/bwrap'] = runtime/'bin/bwrap'
        (root/'usr/local/share/a6/compositor').write_text(args.compositor+'\n')
        for relative, original in replacements.items():
            destination = root/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(original,destination)
            destination.chmod(0o755)
            expected[relative] = digest(original)
        # No manual pages in the handheld image, including retained components.
        for path in list(root.rglob('man')):
            if path.parent.name == 'share':
                if path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
        expected = {name: value for name, value in expected.items() if '/share/man/' not in name}
        # Public source/build metadata only. No home-directory inputs are read.
        report = {'base_sha256':base_sha,'public_overrides':expected,
                  'compositor':args.compositor,
                  'compression':'zstd level 15, 128 KiB blocks','phone_tested':False,
                  'limits':'Five-point fitted udev touch calibration; physical full-screen validation pending.'}
        subprocess.run([str(tools/'squashfs-tools/mksquashfs'),str(unpacked),str(output),
                        '-noappend','-all-root','-root-mode','0755','-no-xattrs',
                        '-comp','zstd','-Xcompression-level','15','-b','131072',
                        '-repro-time','0','-processors','2','-mem','256M','-no-progress'],
                       check=True,stdout=subprocess.DEVNULL)
        verified = Path(temporary)/'verified'
        subprocess.run([str(tools/'squashfs-tools/unsquashfs'),'-no-progress','-processors','2',
                        '-d',str(verified),str(output)],check=True,stdout=subprocess.DEVNULL)
        if args.compositor == 'labwc' and (verified/'graphics-runtime/opt/a6/labwc-runtime').stat().st_mode & 0o777 != 0o755:
            raise ValueError('Labwc runtime is not accessible to the desktop user')
        for relative, expected_hash in expected.items():
            if digest(verified/'graphics-runtime'/relative) != expected_hash:
                raise ValueError('Public desktop override round-trip mismatch')
        if (verified/'graphics-runtime').stat().st_mode & 0o777 != 0o755:
            raise ValueError('Desktop root traversal mode changed')
    report.update(sha256=digest(output),bytes=output.stat().st_size)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Updated compressed desktop built; public overrides verified; private inputs excluded.')

if __name__ == '__main__':
    main()

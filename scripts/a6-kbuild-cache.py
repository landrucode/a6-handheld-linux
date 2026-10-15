#!/usr/bin/env python3
"""Reuse unchanged generated source mtimes and identical resolved Kconfig state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(root):
    names = set()
    for args in (['diff', 'HEAD', '--name-only', '-z'], ['ls-files', '--others', '--exclude-standard', '-z']):
        data = subprocess.check_output(['git', '-C', str(root), *args])
        names.update(os.fsdecode(x) for x in data.split(b'\0') if x)
    return [name for name in sorted(names) if (root / name).is_file()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('capture', 'commit', 'restore'))
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root, output = args.source.resolve(), args.output.resolve()
    cache = output / '.a6-kbuild-cache'
    pending = output / '.a6-kbuild-cache.pending'
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if args.action == 'capture':
        if not (output / 'include/generated/autoconf.h').is_file():
            raise SystemExit('resolved build configuration missing')
        shutil.rmtree(pending, ignore_errors=True)
        pending.mkdir(mode=0o700)
        entries = {}
        for name in sources(root):
            path = root / name
            entries[name] = {'sha256': digest(path), 'mtime_ns': path.stat().st_mtime_ns}
        metadata = {'schema': 1, 'head': head, 'sources': entries,
                    'config_sha256': digest(output / '.config')}
        (pending / 'manifest.json').write_text(json.dumps(metadata))
        shutil.copy2(output / '.config', pending / 'config')
        shutil.copytree(output / 'include/config', pending / 'include-config')
        shutil.copy2(output / 'include/generated/autoconf.h', pending / 'autoconf.h')
        if (output / 'include/generated/rustc_cfg').is_file():
            shutil.copy2(output / 'include/generated/rustc_cfg', pending / 'rustc_cfg')
        return
    if args.action == 'commit':
        if not (pending / 'manifest.json').is_file(): raise SystemExit('no pending successful-build cache')
        shutil.rmtree(cache, ignore_errors=True)
        pending.rename(cache)
        return
    if not (cache / 'manifest.json').is_file():
        print('A6 incremental: cold cache; normal build')
        return
    metadata = json.loads((cache / 'manifest.json').read_text())
    if metadata.get('schema') != 1 or metadata['head'] != head:
        print('A6 incremental: kernel revision changed; normal build')
        return
    reused = 0
    config_inputs_same = True
    current = set(sources(root))
    for name, entry in metadata['sources'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts: raise SystemExit('unsafe cache path')
        path = root / relative
        same = path.is_file() and digest(path) == entry['sha256']
        if same:
            os.utime(path, ns=(path.stat().st_atime_ns, entry['mtime_ns']))
            reused += 1
        elif path.name.startswith(('Kconfig', 'Makefile')):
            config_inputs_same = False
    for name in current - metadata['sources'].keys():
        if Path(name).name.startswith(('Kconfig', 'Makefile')): config_inputs_same = False
    config_same = digest(output / '.config') == metadata['config_sha256']
    if config_same and config_inputs_same:
        # tinyconfig may have generated a different header along the way.
        # Restore the entire validated full-config bundle, never just its date.
        shutil.rmtree(output / 'include/config')
        shutil.copytree(cache / 'include-config', output / 'include/config')
        shutil.copy2(cache / 'autoconf.h', output / 'include/generated/autoconf.h')
        shutil.copy2(cache / 'config', output / '.config')
        if (cache / 'rustc_cfg').is_file():
            shutil.copy2(cache / 'rustc_cfg', output / 'include/generated/rustc_cfg')
    print(f'A6 incremental: reused {reused} unchanged source timestamps; identical config={int(config_same and config_inputs_same)}')


if __name__ == '__main__':
    main()

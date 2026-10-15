#!/usr/bin/env python3
"""Exercise cache invalidation without changing the real kernel tree."""
from pathlib import Path
import os
import subprocess
import tempfile

helper = Path(__file__).with_name('a6-kbuild-cache.py').resolve()


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


with tempfile.TemporaryDirectory() as directory:
    root, output = Path(directory) / 'src', Path(directory) / 'out'
    root.mkdir()
    output.mkdir()
    run('git', 'init', '-q', str(root))
    for name in ('x.c', 'Kconfig.foo'):
        (root / name).write_text('original')
    def commit():
        run('git', '-C', str(root), 'add', '.')
        run('git', '-C', str(root), '-c', 'user.name=Test', '-c',
            'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
    commit()
    for name in ('x.c', 'Kconfig.foo'):
        (root / name).write_text('generated')
    (output / 'include/config').mkdir(parents=True)
    (output / 'include/generated').mkdir()
    (output / '.config').write_text('CONFIG_X=y\n')
    (output / 'include/config/auto.conf').write_text('CONFIG_X=y\n')
    header = output / 'include/generated/autoconf.h'
    header.write_text('#define CONFIG_X 1\n')
    def cache(action):
        return run('python3', str(helper), action, str(root), str(output))
    stamp = (root / 'x.c').stat().st_mtime_ns
    cache('capture')
    assert 'cold cache' in cache('restore'), 'pending cache must not be used'
    cache('commit')
    os.utime(root / 'x.c', ns=(stamp + 1000000, stamp + 1000000))
    header.write_text('different intermediate tinyconfig header')
    assert 'identical config=1' in cache('restore')
    assert (root / 'x.c').stat().st_mtime_ns == stamp
    assert header.read_text() == '#define CONFIG_X 1\n'
    (root / 'x.c').write_text('changed')
    changed = (root / 'x.c').stat().st_mtime_ns
    cache('restore')
    assert (root / 'x.c').stat().st_mtime_ns == changed
    (root / 'Kconfig.foo').write_text('different')
    assert 'identical config=0' in cache('restore')
    (root / 'Kconfig.foo').write_text('generated')
    (output / '.config').write_text('CONFIG_X=n\n')
    assert 'identical config=0' in cache('restore')
    commit()
    assert 'revision changed' in cache('restore')
print('PASS cache invalidation: pending, source content, configuration bundle, Kconfig and kernel revision')

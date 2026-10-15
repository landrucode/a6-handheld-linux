#!/usr/bin/env python3
"""Prepare a recorded native keyboard trial in the mounted RAM desktop."""
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desktop_transport', ROOT / 'scripts/a6-stream-user-desktop.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
LOG = ROOT / ('build/session-logs/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-native-keyboard-setup.log')


def command(text, label, timeout=30):
    output = transport.serial('busybox sh -c ' + shlex.quote(text) + ' && echo ' + label, label, timeout)
    with LOG.open('a') as log:
        log.write(output)
    return output


def as_user(text):
    return ('busybox chroot /tmp/graphics-runtime /proc/1/root/bin/busybox '
            'setpriv --no-new-privs /proc/1/root/bin/busybox su -s /bin/bash a6 -c '
            + shlex.quote(text))


ENV = 'export LC_ALL=C.UTF-8 XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1; '
QUERY = (ENV + 'for instance in "$XDG_RUNTIME_DIR"/hypr/*; do '
         '[[ -S "$instance/.socket.sock" ]] || continue; '
         'export HYPRLAND_INSTANCE_SIGNATURE=${instance##*/}; break; done; ')


def main():
    assert not LOG.exists(), 'keep the earlier setup record; choose a fresh capture name before repeating'
    command('test -d /tmp/graphics-runtime && test -x /tmp/graphics-runtime/usr/local/bin/wvkbd-native && '
            'test ! -e /tmp/graphics-runtime/home/a6/osk-receiver.pid && '
            'grep -q "active=1 result=0 " /sys/firmware/a6_touch_native/status && '
            'test "$(cat /sys/firmware/a6_usb_screen/enabled)" = 0', 'A6_GUI_PREFLIGHT')
    commands = (
        'busybox mount --bind /dev /tmp/graphics-runtime/dev',
        'busybox mount -t proc proc /tmp/graphics-runtime/proc',
        'busybox mount -t sysfs -o ro sysfs /tmp/graphics-runtime/sys',
        'mkdir -p /tmp/graphics-runtime/dev/pts && busybox mount -t devpts devpts /tmp/graphics-runtime/dev/pts',
        'busybox chroot /tmp/graphics-runtime /bin/bash /usr/local/bin/a6-start-desktop prepare',
        'busybox chroot /tmp/graphics-runtime /bin/bash /usr/local/bin/a6-prepare-user-desktop',
        'busybox chroot /tmp/graphics-runtime /proc/1/root/bin/busybox sh /usr/local/bin/a6-label-native-touch',
    )
    for i, text in enumerate(commands):
        command(text, f'A6_GUI_SETUP_{i}')
    command("busybox chroot /tmp/graphics-runtime /bin/bash -c 'nohup "
            "/proc/1/root/bin/busybox setpriv --nnp /proc/1/root/bin/busybox "
            "su -s /bin/bash a6 -c /usr/local/bin/a6-start-user-hyprland "
            "</dev/null >/tmp/hyprland-user.log 2>&1 &'", 'A6_GUI_LAUNCHED')
    command('for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do '
            'test ! -S /tmp/graphics-runtime/run/user/1000/wayland-1 || break; sleep 1; done; '
            'test -S /tmp/graphics-runtime/run/user/1000/wayland-1', 'A6_WAYLAND_READY')
    command(as_user(QUERY + 'for n in {1..30}; do /usr/bin/hyprctl activewindow -j >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'), 'A6_GUI_API_READY', 40)
    config = command(as_user(QUERY + '/usr/bin/hyprctl devices -j | grep -q a6-n42-native-touchscreen || exit 1; '
                    "/usr/bin/hyprctl eval 'hl.config({ input = { follow_mouse = 0, touchdevice = { transform = 6 } } })'; "
                    '/usr/bin/hyprctl getoption input:follow_mouse; '
                    '/usr/bin/hyprctl getoption input:touchdevice:transform; '
                    'test -z "$(/usr/bin/hyprctl configerrors)"'), 'A6_NATIVE_TOUCH_CONFIG')
    for value in (0, 6):
        assert re.search(r'int: ' + str(value) + r'\s+set: true', config), 'native option was not applied'
    command(as_user(ENV + 'nohup /usr/local/bin/wvkbd-native --no-popup -H 300 -L 300 -l simple,special '
                    '--fn "JetBrains Mono 16" </dev/null >/tmp/wvkbd-native.log 2>&1 & '
                    'echo $! > /home/a6/wvkbd-test.pid'), 'A6_KEYBOARD_STARTED')
    command(as_user(ENV + 'nohup /usr/bin/foot /usr/local/bin/a6-osk-receiver '
                    '</dev/null >/tmp/foot-native-proof.log 2>&1 & '
                    'echo $! > /home/a6/osk-receiver.pid'), 'A6_RECEIVER_STARTED')
    command('sleep 2; for file in /tmp/graphics-runtime/home/a6/wvkbd-test.pid '
            '/tmp/graphics-runtime/home/a6/osk-receiver.pid; do '
            'read pid < "$file"; test -r /proc/$pid/status || exit 1; '
            'cat /proc/$pid/comm; cat /proc/$pid/status | busybox grep -E "Uid|Gid|CapEff|NoNewPrivs"; '
            'done', 'A6_CLIENTS_CHECKED')
    # Leave only the receiver's Foot window, avoiding startup-window focus races.
    command(as_user('read receiver < /home/a6/osk-receiver.pid; '
                    'for file in /proc/[0-9]*/comm; do read name < "$file" 2>/dev/null || continue; '
                    '[[ "$name" == foot ]] || continue; pid=${file#/proc/}; pid=${pid%/comm}; '
                    '[[ "$pid" == "$receiver" ]] || kill "$pid" 2>/dev/null || true; done'), 'A6_RECEIVER_ONLY')
    output = command(as_user(QUERY + '/usr/bin/hyprctl activewindow -j'), 'A6_RECEIVER_FOCUS')
    start, end = re.search(r'^\{', output, re.M).start(), output.rfind('}') + 1
    active = json.loads(output[start:end])
    pid_output = command('cat /tmp/graphics-runtime/home/a6/osk-receiver.pid', 'A6_RECEIVER_PID')
    pids = [int(line) for line in pid_output.replace('\r', '').splitlines() if line.isdigit()]
    assert len(pids) == 1 and active['pid'] == pids[0], 'test receiver is not focused'
    command(as_user(QUERY + '/usr/bin/hyprctl layers -j; /usr/bin/hyprctl devices -j'), 'A6_GUI_INPUT_AND_LAYER')
    command('test ! -e /tmp/a6-native-gui-events.bin && '
            "busybox sh -c 'busybox dd if=/dev/input/event0 of=/tmp/a6-native-gui-events.bin "
            "bs=16 count=4096 2>/tmp/a6-native-gui-events.err & "
            "echo $! > /tmp/a6-native-gui-events.pid'", 'A6_GUI_RECORDING')
    command('cat /sys/firmware/a6_touch_native/status', 'A6_GUI_TOUCH_READY')
    print('Keyboard and focused receiver checked; bounded evdev recorder armed. Evidence:', LOG)


if __name__ == '__main__':
    main()

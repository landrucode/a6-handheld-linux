#!/usr/bin/env python3
"""Prove shell command execution on the verified A6 USB port, without disk writes."""
import argparse
import fcntl
import hashlib
import struct
import os
import re
from pathlib import Path
import secrets
import select
import sys
import termios
import time
import tty

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('device')
parser.add_argument('--raw-log', type=Path, help='save exact received USB bytes to a new host file')
modes = parser.add_mutually_exclusive_group()
modes.add_argument('--builtins', action='store_true', help='inspect using shell built-ins only')
modes.add_argument('--fork-check', action='store_true', help='compare built-in subshell and external true')
modes.add_argument('--mmu-test', type=Path, help='upload a static ARM test to RAM, verify SHA256, and run once')
modes.add_argument('--userspace-test', type=Path, help='upload and run the six bounded userspace-service checks')
modes.add_argument('--framebuffer-test', type=Path, help='validate fbdev mappings and draw a labelled native display test')
modes.add_argument('--rollover', action='store_true', help='288 fork/exec cycles; ONLY on rollover/full-TLBI candidate')
modes.add_argument('--smoke', action='store_true', help='32 bounded fork/exec cycles and one pipeline')
args = parser.parse_args()
node = Path(args.device)
assert node.parent == Path('/dev') and node.name.startswith('ttyACM')
usb = Path('/sys/class/tty', node.name, 'device').resolve()
usb = next(p for p in (usb, *usb.parents) if (p / 'idVendor').exists())
assert usb.name == '1-5'
assert ((usb / 'idVendor').read_text().strip(), (usb / 'idProduct').read_text().strip()) in {('1209', '0001'), ('0525', 'a4aa')}
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
raw_log = None
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Exclude other serial opens while this client owns the terminal.
    fcntl.ioctl(fd, termios.TIOCEXCL)
    if args.raw_log:
        raw_log = args.raw_log.open("xb")
    tty.setraw(fd, termios.TCSANOW)
    token = secrets.token_hex(16)
    expected = f'A6-SHELL-{token}'.encode()
    # The expected string never appears verbatim in transmitted text: neither
    # terminal echo nor the former PID1 echo exerciser can satisfy this test.
    command = f"printf '\\n%s%s\\n' 'A6-SHELL-' '{token}'\n".encode()
    data = bytearray()
    def capture():
        try:
            chunk = os.read(fd, 8192)
        except BlockingIOError:
            return
        if not chunk:
            raise RuntimeError('USB disconnected')
        if raw_log:
            raw_log.write(chunk)
            raw_log.flush()
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        data.extend(chunk)
    def send_all(command):
        offset = 0
        deadline = time.monotonic() + 20
        while offset < len(command) and time.monotonic() < deadline:
            readable, writable, _ = select.select([fd], [fd], [], 0.5)
            if readable:
                capture()
            if writable:
                try:
                    offset += os.write(fd, command[offset:])
                except BlockingIOError:
                    continue
        if offset != len(command):
            raise RuntimeError(f'USB write timed out ({offset}/{len(command)} bytes); no execution claim')
    def receive_until(marker, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker in data:
                return
            if select.select([fd], [], [], 0.5)[0]:
                capture()
        raise RuntimeError('shell response timed out; no execution claim')
    # Cancel any partial line left by startup echo or an interrupted probe,
    # and wait for the shell before sending the execution challenge.
    send_all(b'\x03\n')
    receive_until(b'A6-RAM #')
    data.clear()
    send_all(command)
    receive_until(expected)
    print('\nPASS: shell executed the fresh-token command.', flush=True)
    data.clear()
    if args.mmu_test or args.userspace_test or args.framebuffer_test:
        test_kind = 'FRAMEBUFFER' if args.framebuffer_test else ('USERSPACE' if args.userspace_test else 'MMU')
        payload = (args.framebuffer_test or args.userspace_test or args.mmu_test).read_bytes()
        if not (0 < len(payload) <= 65536 and payload[:7] == b'\x7fELF\x01\x01\x01'
                and struct.unpack_from('<H', payload, 18)[0] == 40
                and struct.unpack_from('<I', payload, 36)[0] & 0x600 == 0x200):
            raise RuntimeError('test must be a small ARM soft-float ELF')
        phoff = struct.unpack_from('<I', payload, 28)[0]
        entsize, count = struct.unpack_from('<HH', payload, 42)
        if any(struct.unpack_from('<I', payload, phoff+i*entsize)[0] == 3 for i in range(count)):
            raise RuntimeError('test must be static')
        def transaction(body, label):
            data.clear()
            marker = f'A6-XFER-{token}-{label}'.encode()
            send_all((body + "; xfer_status=$?; " +
                      f"printf '\\n%s%s %s\\n' 'A6-XFER-' '{token}-{label}' \"$xfer_status\"\n").encode())
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                lines = bytes(data).replace(b'\r', b'').split(b'\n')[:-1]
                records = [line for line in lines if line.startswith(marker + b' ')]
                if records:
                    if records != [marker + b' 0']:
                        raise RuntimeError(f'transfer command failed: {records!r}')
                    return lines
                if select.select([fd], [], [], 0.5)[0]:
                    capture()
            raise RuntimeError('transfer status timed out')
        # Refuse uploads if a persistent/unrecognized filesystem is mounted.
        transaction("ram_ok=1; while read -r src dst fs rest; do "
                    "case \"$fs\" in rootfs|devtmpfs|proc|sysfs) ;; *) ram_ok=0;; esac; "
                    "done < /proc/mounts; test \"$ram_ok\" = 1 && test -d /tmp && test ! -L /tmp", 'ram')
        directory = f'/tmp/a6-{test_kind.lower()}-{token}'
        target = directory + '/test'
        transaction(f'/bin/busybox mkdir {directory}', 'mkdir')
        for offset in range(0, len(payload), 128):
            escaped = ''.join(f'\\{byte:03o}' for byte in payload[offset:offset+128])
            transaction(f"printf '{escaped}' >> {target}", str(offset))
        lines = transaction(f'/bin/busybox sha256sum {target}', 'hash')
        digest = hashlib.sha256(payload).hexdigest()
        if f'{digest}  {target}'.encode() not in lines:
            raise RuntimeError('uploaded test hash mismatch; not executing')
        transaction(f'/bin/busybox chmod 700 {target}', 'chmod')
        data.clear()
        send_all((f"{target}; printf '{test_kind} STATUS %s\\n' \"$?\"; " +
                  f"printf '\\n%s%s\\n' 'A6-END-' '{token}'\n").encode())
        receive_until(f'A6-END-{token}'.encode())
        lines = bytes(data).replace(b'\r', b'').split(b'\n')
        required = [b'PASS mprotect ACCERR', b'PASS munmap MAPERR',
                    b'PASS remap zero/guards', b'PASS fork COW isolation',
                    b'A6-MMU PASS 4', b'MMU STATUS 0']
        if args.userspace_test:
            required = [b'PASS unix socketpair', b'PASS epoll/eventfd',
                        b'PASS timerfd expiration', b'PASS signalfd',
                        b'PASS inotify event', b'PASS POSIX timer lifecycle',
                        b'A6 USERSPACE PASS 6', b'USERSPACE STATUS 0']
        if args.framebuffer_test:
            required = [b'PASS fbdev identity/geometry',
                        b'PASS fbdev mmap bounds/nonexec/coherence',
                        b'A6 FRAMEBUFFER DRAW PASS', b'FRAMEBUFFER STATUS 0']
        if any(line not in lines for line in required):
            raise RuntimeError(f'{test_kind} test failed; stop and inspect raw log')
        print('PASS: framebuffer checks and drawing; visual confirmation still needed.' if args.framebuffer_test else
              ('PASS: six userspace-service checks.' if args.userspace_test else
               'PASS: four MMU semantic checks; no rollover/cache claim.'))
        sys.exit(0)
    inspection = (
        "printf 'SHELL PID %s\\n' \"$$\"; "
        "for f in /proc/version /proc/$$/status /proc/$$/maps /proc/mounts "
        "/sys/class/power_supply/*/capacity; do "
        "if test -r \"$f\"; then printf 'FILE %s\\n' \"$f\"; "
        "while IFS= read -r line; do printf '%s\\n' \"$line\"; done < \"$f\"; fi; done; "
        "printf 'BATTERY PATHS %s\\n' /sys/class/power_supply/*/capacity; "
        if args.builtins else
        "uname -a; printf 'UNAME STATUS %s\\n' \"$?\"; "
        "echo PROCESSES; ps; printf 'PS STATUS %s\\n' \"$?\"; "
        "echo MOUNTS; cat /proc/mounts; printf 'CAT STATUS %s\\n' \"$?\"; "
    )
    command = (inspection +
               f"printf '\\n%s%s\\n' 'A6-END-' '{token}'\n").encode()
    if args.fork_check:
        command = ("probe_parent=parent; (probe_parent=child; printf 'SUBSHELL %s\\n' \"$probe_parent\"); "
                   "printf 'SUBSHELL STATUS %s PARENT %s\\n' \"$?\" \"$probe_parent\"; "
                   "/bin/busybox true; printf 'EXEC STATUS %s\\n' \"$?\"; "
                   f"printf '\\n%s%s\\n' 'A6-END-' '{token}'\n").encode()
    if args.smoke:
        command = ("smoke_parent=parent; i=0; "
                   "while test \"$i\" -lt 32; do "
                   "(smoke_parent=child; test \"$smoke_parent\" = child) && /bin/busybox true || break; "
                   "test \"$smoke_parent\" = parent || break; i=$((i+1)); done; "
                   "printf 'FORK EXEC CYCLES %s\\n' \"$i\"; "
                   "printf abcdef | /bin/busybox wc -c; printf 'PIPE STATUS %s\\n' \"$?\"; "
                   f"printf '\\n%s%s\\n' 'A6-END-' '{token}'\n").encode()
    if args.rollover:
        command = ("roll_parent=parent; i=0; "
                   "while test \"$i\" -lt 288; do "
                   "(roll_parent=child; test \"$roll_parent\" = child) && /bin/busybox true || break; "
                   "test \"$roll_parent\" = parent || break; i=$((i+1)); done; "
                   "printf 'ROLLOVER CYCLES %s PARENT %s\\n' \"$i\" \"$roll_parent\"; "
                   "/bin/busybox dmesg; printf 'DMESG STATUS %s\\n' \"$?\"; "
                   f"printf '\\n%s%s\\n' 'A6-END-' '{token}'\n").encode()
    send_all(command)
    receive_until(f'A6-END-{token}'.encode(), timeout=240 if args.rollover else 20)
    if b'stack smashing detected' in data or b'Aborted' in data or b'not found' in data:
        raise RuntimeError('shell command execution proven, but inspection/child commands failed')
    lines = bytes(data).replace(b'\r', b'').split(b'\n')
    required = ([b'ROLLOVER CYCLES 288 PARENT parent', b'DMESG STATUS 0'] if args.rollover else
                [b'FORK EXEC CYCLES 32', b'6', b'PIPE STATUS 0'] if args.smoke else
                [b'SUBSHELL child', b'SUBSHELL STATUS 0 PARENT parent', b'EXEC STATUS 0']
                if args.fork_check else [] if args.builtins else
                [b'UNAME STATUS 0', b'PS STATUS 0', b'CAT STATUS 0'])
    if any(line not in lines for line in required):
        raise RuntimeError('missing successful command statuses; no inspection pass')
    if args.rollover:
        entered = set(re.findall(rb'A6 ROLLOVER TLBI ENTER generation=([0-9a-f]+)', data))
        returned = set(re.findall(rb'A6 ROLLOVER TLBI RETURN generation=([0-9a-f]+)', data))
        if len(returned) < 2 or entered != returned:
            raise RuntimeError('missing paired full-TLBI markers for at least two ASID generations')
        print(f'PASS: 288 cycles; paired full-TLBI markers for {len(returned)} generations.')
    else:
        print('\nPASS: shell executed fresh-token command and completed read-only inspection.')
finally:
    # Leave host echo disabled: enabling it on close feeds device output back
    # into the still-running shell. An interactive terminal sets its own mode.
    if raw_log:
        raw_log.close()
    os.close(fd)

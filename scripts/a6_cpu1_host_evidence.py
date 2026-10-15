"""Local host-side USB evidence for attended CPU1 trials; never a phone call."""
from datetime import datetime, timezone
import subprocess


def timestamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def run_record(stream, title, command):
    stream.write(f'\n{title} utc={timestamp()}\n')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8)
        stream.write(f'exit_code={result.returncode}\n{result.stdout}{result.stderr}')
    except (OSError, subprocess.TimeoutExpired) as error:
        stream.write(f'capture_error={error}\n')
    stream.flush()


def begin(capture):
    since = timestamp()
    with capture.with_suffix('.host.txt').open('w') as stream:
        stream.write(f'trial_start_utc={since}\n')
        run_record(stream, 'usb_before', ['lsusb'])
    return since


def finish(capture, since):
    with capture.with_suffix('.host.txt').open('a') as stream:
        run_record(stream, 'usb_after', ['lsusb'])
        run_record(stream, 'host_kernel_since_start',
                   ['journalctl', '-k', '--since', since, '--no-pager', '-o', 'short-iso'])

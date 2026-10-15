#!/usr/bin/env bash
# One-boot audio observation; retain the accepted image and native bundle.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
destination="${A6_AUDIO_CANDIDATE_DIR:-build/audio-fifo-candidate}"
[[ "$destination" == build/* && "$destination" != *..* ]]
backup="build/audio-fifo-backup-$(date -u +%s)"
mkdir -p "$destination" "$backup"
if pgrep -x make >/dev/null; then
    echo 'Another build is running; shared kernel checkout must be serialized.' >&2
    exit 1
fi
exec 9>build/audio-kernel-build.lock
flock -n 9
cp -a build/wifi-native "$backup/"
images=(a6-wifi-brcmfmac.img3 a6-wifi-combined.img3
    a6-linux-low-battery-boot-defaults-touch-ram-root-frames-native-wifi-ehci-enum-smp-first-scheduling.img3)
for image in "${images[@]}"; do cp -a "build/arm/$image" "$backup/"; done
restore() {
    rsync -a --exclude=/acm.sock "$backup/wifi-native/" build/wifi-native/
    for image in "${images[@]}"; do cp -a "$backup/$image" "build/arm/$image"; done
}
trap restore EXIT
cc -std=gnu11 -O0 scripts/test-a6-audio-fifo.c -o "$destination/test-audio-fifo"
"$destination/test-audio-fifo"
if [[ "${A6_AUDIO_AMP_ID:-0}" == 1 ]]; then
    cc -std=gnu11 -O0 -DA6_AUDIO_AMP_ID scripts/test-a6-audio-fifo.c -o "$destination/test-audio-amp"
    "$destination/test-audio-amp"
    python3 scripts/verify-a6-stock-audio.py > "$destination/stock-audio.private.json"
    python3 scripts/verify-a6-stock-touch-pwm.py > "$destination/stock-nclk.private.json"
fi
if [[ "${A6_AUDIO_TONE:-0}" == 1 ]]; then
    export A6_CAPTURE_AUDIO=1 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1
    build/audio-research/trace-venv/bin/python scripts/prepare-a6-speaker-sequence.py
    build/audio-research/trace-venv/bin/python scripts/prepare-a6-speaker-sequence.py --amp-master
    build/audio-research/trace-venv/bin/python scripts/prepare-a6-speaker-sequence.py --amp-master --stock44100
    build/audio-research/trace-venv/bin/python scripts/prepare-a6-speaker-sequence.py --supply-monitors
    build/audio-research/trace-venv/bin/python scripts/prepare-a6-speaker-sequence.py --supply-monitors --amp-master
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-speaker-route.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-mca-format.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-speaker44.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-audio-nco.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-codec-control.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-codec-iis.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-codec-profile.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-codec-route.py
    build/audio-research/trace-venv/bin/python scripts/test-a6-stock-codec-mca.py
    build/audio-research/trace-venv/bin/python scripts/prepare-a6-codec-sequence.py
    cc -std=gnu11 -O0 scripts/test-a6-audio-codec.c -o "$destination/test-audio-codec"
    "$destination/test-audio-codec"
    python3 scripts/test-a6-audio-capture.py
    cc -std=gnu11 -O0 scripts/test-a6-audio-tone.c -o "$destination/test-audio-tone"
    "$destination/test-audio-tone"
fi
if [[ "${A6_AUDIO_ALSA:-0}" == 1 ]]; then
    mic_args=(--all-banks)
    python3 scripts/prepare-a6-mic-sequence.py build/audio-research/ios-mic-recording-decoded.private.json "${mic_args[@]}"
    python3 scripts/test-a6-audio-alsa.py
    python3 scripts/test-a6-audio-pcm-prepare.py
    python3 scripts/test-a6-audio-pcm-free.py
    if [[ "${A6_AUDIO_RAW_CAPTURE:-0}" == 1 ]]; then python3 scripts/test-a6-audio-raw.py; python3 scripts/test-a6-audio-codec-restore.py; python3 scripts/test-a6-audio-raw-lifetime.py; python3 scripts/test-a6-audio-codec-clear.py; fi
fi
python3 scripts/test-a6-usb-upload-guard.py
python3 scripts/test-a6-provision-recovery.py
python3 scripts/test-a6-wifi-download-image-bound.py
A6_AUDIO_FIFO_DISCOVER=1 bash scripts/build-a6-wifi-native.sh > "$destination/build.private.log" 2>&1
cp -a build/arm/a6-wifi-brcmfmac.img3 "$destination/a6-audio-fifo.img3"
cp -a build/wifi-native "$destination/"
cp build/linux-a6-low-battery-boot-defaults-touch-ram-root-frames-native-wifi-ehci-enum-smp-first-scheduling/.config "$destination/kernel.config"
if [[ "${A6_AUDIO_TONE:-0}" == 1 ]]; then
    python3 - <<'VERIFY_TONE'
from pathlib import Path
import struct
kernel=Path('build/linux-a6-low-battery-boot-defaults-touch-ram-root-frames-native-wifi-ehci-enum-smp-first-scheduling/vmlinux').read_bytes()
config=struct.pack('<12I',0x1010,0x0f107005,1,0,0x208,0xd,0x007f0004,1,0x10a,0xd,0x007f0004,6)
import os
if os.environ.get('A6_AUDIO_ALSA')=='1':
    assert 'CONFIG_HIGH_RES_TIMERS=y' in Path('build/linux-a6-low-battery-boot-defaults-touch-ram-root-frames-native-wifi-ehci-enum-smp-first-scheduling/.config').read_text()
    assert b'N42 MCA0 speaker and IIS0 microphone' in kernel
    assert b'Speaker Playback Volume' in kernel
    import sys
    print('PASS: compiled ALSA playback, capture and mixer present')
    sys.exit(0)
else:
    assert config in kernel, 'compiled eight-slot audio configuration missing'
if os.environ.get('A6_AUDIO_ALSA')!='1':
    assert b'stock-speaker44-sweep-%u-allslots-%u' in kernel, 'GPIO/all-slot sweep missing'
assert b'stock-speaker44-ios-%u' in kernel and b'ios_playback_route=%u' in kernel, 'captured playback route candidate missing'
assert b'stock-speaker44-level-%u' in kernel, 'observed stock44 candidate missing'
assert struct.pack('<12I',0x1010,0x0f107000,1,0,0x108,0xd,0x00170004,1,0x10a,0xd,0x002b0004,3) in kernel, 'observed stock44 configuration missing'
assert b'codec-amp-level-%u-variant-%u' in kernel, 'full-scale ladder missing'
assert b'codec-amp-variant-%u' in kernel and b'codec_reference_2e_2f_24f_13=' in kernel, 'combined reference variant missing'
assert b'codec-receiver-enable-restore' in kernel and b'codec_write_readbacks' in kernel, 'compiled receiver variant missing'
assert struct.pack('<12I',0x1010,0x0f107005,1,0,0x208,0xd,0x007b0004,255,0x10a,0xd,0x00030004,0) in kernel, 'compiled codec MCA reference format missing'
assert b'amp_alive9=' in kernel, 'compiled GPIO9 diagnostic missing'
print('PASS: compiled eight-slot tone and GPIO9 diagnostics present')
VERIFY_TONE
fi
sha256sum "$destination/a6-audio-fifo.img3" "$destination/wifi-native/modules.tar.gz"

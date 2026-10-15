#!/usr/bin/env bash
# One-boot audio observation; retain the accepted image and native bundle.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
destination=build/audio-gate-candidate
backup="build/audio-gate-backup-$(date -u +%s)"
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
    cp -a "$backup/wifi-native/." build/wifi-native/
    for image in "${images[@]}"; do cp -a "$backup/$image" "build/arm/$image"; done
}
trap restore EXIT
cc -std=gnu11 -O0 scripts/test-a6-audio-gates.c -o "$destination/test-audio-gates"
"$destination/test-audio-gates"
A6_AUDIO_GATE_OBSERVE=1 bash scripts/build-a6-wifi-native.sh > "$destination/build.private.log" 2>&1
cp -a build/arm/a6-wifi-brcmfmac.img3 "$destination/a6-audio-gates.img3"
cp -a build/wifi-native "$destination/"
cp build/linux-a6-low-battery-boot-defaults-touch-ram-root-frames-native-wifi-ehci-enum-smp-first-scheduling/.config "$destination/kernel.config"
sha256sum "$destination/a6-audio-gates.img3" "$destination/wifi-native/modules.tar.gz"

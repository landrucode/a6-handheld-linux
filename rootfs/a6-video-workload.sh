#!/bin/bash
# Run as the desktop user; use the same visible software path as the panel.
set -euo pipefail
umask 077
[[ $(id -u) == 1000 ]]
: >/tmp/a6-video-measure.private.log
for height in 360 480; do
 /usr/local/bin/a6-launch-video "/usr/local/share/a6/video-${height}p.mp4" \
  >"/tmp/a6-video-${height}p.private.log" 2>&1
 printf 'A6_VIDEO_PLAYBACK_EXIT_OK %sp\n' "$height"
done

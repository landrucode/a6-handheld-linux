#!/usr/bin/env bash
# Public synthetic fixture; no phone recordings or firmware inputs.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo/build/local-media"
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=640x360:rate=15 \
 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 10 \
 -c:v libx264 -profile:v baseline -pix_fmt yuv420p -crf 30 \
 -c:a aac -b:a 48k -movflags +faststart -y "$repo/build/local-media/local-video.mp4"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames \
 -of json "$repo/build/local-media/local-video.mp4" >"$repo/build/local-media/fixture.json"
python3 - "$repo/build/local-media/fixture.json" <<'PY'
import json,sys
streams=json.load(open(sys.argv[1]))['streams']
assert any(s.get('codec_name')=='h264' and s.get('width')==640 and s.get('height')==360 and s.get('nb_frames')=='150' for s in streams)
assert any(s.get('codec_name')=='aac' for s in streams)
PY

for size in 640x360 854x480; do
 height=${size#*x}
 ffmpeg -hide_banner -loglevel error -f lavfi -i "testsrc2=size=$size:rate=30" \
  -f lavfi -i sine=frequency=440:sample_rate=48000 -t 30 \
  -c:v libx264 -profile:v baseline -pix_fmt yuv420p -crf 28 \
  -c:a aac -b:a 48k -movflags +faststart -y "$repo/build/local-media/video-${height}p.mp4"
done

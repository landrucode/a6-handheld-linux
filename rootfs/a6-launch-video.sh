#!/bin/bash
# UID1000 handheld video launcher; URLs and diagnostics stay in RAM.
set -euo pipefail
umask 077
media=/opt/a6/media-runtime/usr
export LD_LIBRARY_PATH="$media/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="/usr/local/bin:$media/bin:$PATH"
export PYTHONHOME=/opt/a6/media-runtime/usr
# PipeWire dynamically loads SPA modules; the ELF library closure alone is
# insufficient. Reuse the matching packaged native audio runtime.
audio=/opt/a6/audio-runtime
export SPA_PLUGIN_DIR="$audio/usr/lib/spa-0.2"
export PIPEWIRE_MODULE_DIR="$audio/usr/lib/pipewire-0.3"
export PIPEWIRE_CONFIG_DIR="$audio/config/pipewire"
export ALSA_CONFIG_PATH="$audio/usr/share/alsa/alsa.conf"
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
export SSL_CERT_FILE=/etc/ssl/cert.pem
url=${1:-/usr/local/share/a6/video-360p.mp4}
exec "$media/bin/mpv" --no-config --profile=sw-fast --hwdec=no --vo=wlshm --ao=pipewire,alsa \
 --vd-lavc-threads=2 --cache=yes --demuxer-max-bytes=8MiB \
 --ytdl-format='best[height<=480][vcodec^=avc1]/bestvideo[height<=480][vcodec^=avc1]+bestaudio' \
 --script=/usr/local/share/a6/video-measure.lua -- "$url"

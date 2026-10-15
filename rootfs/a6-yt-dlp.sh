#!/bin/bash
# Use the packaged Python, regardless of the base root's Python installation.
set -euo pipefail
export PYTHONHOME=/opt/a6/media-runtime/usr
export LD_LIBRARY_PATH=/opt/a6/media-runtime/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
exec /opt/a6/media-runtime/usr/bin/python3.14 -m yt_dlp "$@"

#!/bin/bash
# RAM-only audio session. Execute as the desktop's UID1000.
set -euo pipefail
[[ $(id -u) == 1000 ]]
umask 077
export XDG_RUNTIME_DIR=/run/user/1000
prefix=/opt/a6/audio-runtime/usr
export PATH="$prefix/bin:/usr/bin:/bin"
export LD_LIBRARY_PATH="$prefix/lib"
export PIPEWIRE_MODULE_DIR="$prefix/lib/pipewire-0.3"
export SPA_PLUGIN_DIR="$prefix/lib/spa-0.2"
export PIPEWIRE_CONFIG_DIR=/opt/a6/audio-runtime/config/pipewire
export ALSA_CONFIG_PATH="$prefix/share/alsa/alsa.conf"
export WIREPLUMBER_DATA_DIR="$prefix/share/wireplumber"
export WIREPLUMBER_MODULE_DIR="$prefix/lib/wireplumber-0.5"
export WIREPLUMBER_CONFIG_DIR=/opt/a6/audio-runtime/config/wireplumber
mode=${1:-start}
case "$mode" in
 start)
  [[ ! -S "$XDG_RUNTIME_DIR/pipewire-0" ]]
  exec dbus-run-session --dbus-daemon="$prefix/bin/dbus-daemon" --config-file="$prefix/share/dbus-1/session.conf" -- /usr/local/bin/a6-audio-session daemon
  ;;
 daemon)
  pipewire >"$XDG_RUNTIME_DIR/a6-pipewire.log" 2>&1 &
  pw_pid=$!
  wp_pid=
  trap '[[ -z "$wp_pid" ]] || kill "$wp_pid" 2>/dev/null || :; kill "$pw_pid" 2>/dev/null || :; wait || :' EXIT
  for ((n=0;n<100;n++)); do
   [[ ! -S "$XDG_RUNTIME_DIR/pipewire-0" ]] || break
   kill -0 "$pw_pid"
   sleep .1
  done
  [[ -S "$XDG_RUNTIME_DIR/pipewire-0" ]]
  wireplumber >"$XDG_RUNTIME_DIR/a6-wireplumber.log" 2>&1 &
  wp_pid=$!
  wait "$pw_pid"
  ;;
 play)
  [[ $# == 2 && -r "$2" ]]
  echo "A6_PIPEWIRE_PLAY uid=$(id -u)"
  exec timeout -s INT 30 pw-play --target a6-speaker "$2"
  ;;
 record)
  [[ $# == 2 ]]
  echo "A6_PIPEWIRE_RECORD uid=$(id -u) duration=5"
  # Full-bank prepare can take several seconds; time actual data, not startup.
  : > "$2"
  pw-record --target a6-microphone --rate 44100 --channels 1 --format s16 "$2" &
  record_pid=$!
  trap 'kill -INT "$record_pid" 2>/dev/null || :; wait "$record_pid" 2>/dev/null || :' EXIT
  for ((n=0;n<200;n++)); do
   kill -0 "$record_pid" 2>/dev/null || break
   [[ ! -f "$2" || $(stat -c %s "$2") -le 44 ]] || break
   sleep .1
  done
  [[ -f "$2" && $(stat -c %s "$2") -gt 44 ]] || { echo "A6_CAPTURE_FAILED no PCM data" >&2; exit 1; }
  echo A6_PIPEWIRE_RECORD_STARTED
  sleep 5
  kill -INT "$record_pid"
  set +e
  wait "$record_pid"
  result=$?
  set -e
  trap - EXIT
  # pw-cat 1.6.9 returns 1 on our deliberate SIGINT (only drain returns 0).
  [[ $result == 0 || $result == 1 ]] || exit "$result"
  # Release the codec before a following speaker play changes shared clocks.
  nodes=$(pw-cli ls Node)
  mic_id=
  node_id=
  while IFS= read -r line; do
    if [[ $line =~ id[[:space:]]+([0-9]+),[[:space:]]+type ]]; then
      node_id=${BASH_REMATCH[1]}
    elif [[ $line == *'node.name = "a6-microphone"'* ]]; then
      mic_id=$node_id
    fi
  done <<< "$nodes"
  [[ $mic_id =~ ^[0-9]+$ ]]
  pw-cli send-command "$mic_id" Suspend '{}'
  ;;
 *) exit 2 ;;
esac

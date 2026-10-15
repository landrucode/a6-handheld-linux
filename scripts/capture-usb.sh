#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
if [[ -z "$mode" ]]; then
  printf 'usage: %s <normal|recovery|dfu|pwned-dfu>\n' "$0" >&2
  exit 2
fi

case "$mode" in
  normal|recovery|dfu|pwned-dfu) ;;
  *)
    printf 'invalid mode: %s\n' "$mode" >&2
    exit 2
    ;;
esac

if ! command -v lsusb >/dev/null 2>&1; then
  printf 'lsusb is required (provided by usbutils on Arch Linux).\n' >&2
  exit 1
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="${A6_LOG_DIR:-logs/usb}"
mkdir -p "$out_dir"
out="$out_dir/${ts}-${mode}.txt"

{
  printf 'timestamp_utc=%s\n' "$ts"
  printf 'declared_mode=%s\n' "$mode"
  printf 'host=%s\n' "$(uname -a)"
  printf '\n[lsusb]\n'
  lsusb
  printf '\n[apple_matches]\n'
  lsusb | grep -iE 'Apple|05ac:' || true
  printf '\n[usb-devices]\n'
  if command -v usb-devices >/dev/null 2>&1; then
    usb-devices
  else
    printf 'usb-devices unavailable\n'
  fi
} | tee "$out"

printf '\nSaved %s\n' "$out"
printf 'Review the declared mode against the USB identifiers before committing the log.\n'

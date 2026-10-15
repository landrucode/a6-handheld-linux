#!/usr/bin/env bash
set -euo pipefail

printf 'a6-linux host preflight\n'
printf '======================\n'
printf 'date_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'uname: %s\n' "$(uname -a)"
printf 'machine: %s\n' "$(uname -m)"

if [[ -r /etc/os-release ]]; then
  printf '\n[os-release]\n'
  cat /etc/os-release
fi

printf '\n[commands]\n'
commands=(git make gcc clang python3 lsusb usb-devices journalctl dmesg)
for cmd in "${commands[@]}"; do
  if path="$(command -v "$cmd" 2>/dev/null)"; then
    printf '%-12s %s\n' "$cmd" "$path"
  else
    printf '%-12s MISSING\n' "$cmd"
  fi
done

printf '\n[versions]\n'
for cmd in git make gcc clang python3; do
  if command -v "$cmd" >/dev/null 2>&1; then
    case "$cmd" in
      python3) "$cmd" --version 2>&1 | head -n 1 ;;
      *) "$cmd" --version 2>&1 | head -n 1 ;;
    esac
  fi
done

printf '\n[usb-apple]\n'
if command -v lsusb >/dev/null 2>&1; then
  lsusb | grep -iE 'Apple|05ac:' || printf 'No Apple USB device visible.\n'
else
  printf 'lsusb unavailable. Install usbutils before the hardware session.\n'
fi

printf '\nThis script is read-only. It does not enter recovery/DFU, install packages, or modify the phone.\n'

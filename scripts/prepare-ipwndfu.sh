#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/axi0mX/ipwndfu.git"
revision="0e28932ec6a2a570b10fd77e50bda4216418cd98"
deps_dir="${A6_DEPS_DIR:-.deps}"
target="$deps_dir/ipwndfu"

mkdir -p "$deps_dir"

if [[ ! -d "$target/.git" ]]; then
  git clone --no-checkout "$repo_url" "$target"
fi

git -C "$target" fetch --quiet origin "$revision"
git -C "$target" checkout --detach "$revision"

actual="$(git -C "$target" rev-parse HEAD)"
if [[ "$actual" != "$revision" ]]; then
  printf 'revision mismatch: expected %s, got %s\n' "$revision" "$actual" >&2
  exit 1
fi

printf 'ipwndfu pinned at %s\n' "$actual"
printf '\n[python]\n'
for py in python2 python; do
  if command -v "$py" >/dev/null 2>&1; then
    printf '%s: ' "$py"
    "$py" --version 2>&1 || true
  else
    printf '%s: MISSING\n' "$py"
  fi
done

printf '\n[libusb]\n'
if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists libusb-1.0; then
  printf 'libusb-1.0: %s\n' "$(pkg-config --modversion libusb-1.0)"
else
  printf 'libusb-1.0 development metadata not detected via pkg-config.\n'
fi

printf '\nNo exploit has been executed. This script only fetches the pinned source and reports host prerequisites.\n'

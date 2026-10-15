# Reproducible desktop builds

`scripts/build-a6-handheld-from-source.py` builds the desktop and browser
images from pinned upstream sources and signature-checked Arch Linux ARM
packages. It needs no earlier image, no prepared runtime directory and no
signing key. The kernel and boot images are separate and still need Apple
files you extract yourself (see [BUILDING.md](../BUILDING.md)).

## Results

Two empty checkouts in different directories, on the same host with the same
package cache, produced byte-identical images. All 22 build stages passed and
neither source tree was modified. The images built from this
release are:

| Image | Bytes | SHA-256 |
| --- | ---: | --- |
| Desktop | 230,637,568 (219.95 MiB) | `18e3651bc14b5652a793437228b1fd21c0c85905a2f8e335b66bc54df99983b7` |
| Browser | 139,329,536 (132.88 MiB) | `bc4ab804c1c9ccac355320e4186d9f3edbbe7735d96f4223ff381f718c6b0b63` |

The host had Clang 22.1.8, ffmpeg n9.0.1 and Python 3.15.0. Other compiler or
codec versions may give different bytes, and rolling mirrors may drop the
locked package files. The `--package-cache` option takes a directory of the
original signed downloads for that case.

The browser image matches the one tested on the phone byte for byte. The
desktop image differs from the tested one in four places, none of them
programs or user configuration: the unused root user's Foot config,
whitespace in a font configuration file, and two empty directories that were
removed.

## Problems the clean build found

Building from nothing exposed dependencies that earlier builds had picked up
from leftover images:

- The audio packages came from rolling snapshots. Their 19 packages and the
  signing key are now pinned.
- The browser and user tools needed a rolling package database. Checked-in
  lock files now set the package list.
- The video player relied on libraries left over from an earlier desktop
  image. They now come from the lock files.
- labwc was missing an ARM SVG library (`librsvg`). The builder now checks
  every ARM program's library dependencies and adds the missing ones from
  verified packages.
- The browser build read the private signing key. Signing is now a separate,
  explicit step.
- Build paths are normalised and file timestamps fixed so that output is
  repeatable.

## Host checks

`scripts/check-a6-handheld-elf.py` unpacks the images and runs 14 checks under
`qemu-arm-static`: Bash, Foot, the keyboard, labwc, the panel's libraries,
mpv, PipeWire, SSH, `ip`, `htop`, `tmux`, Epiphany, bubblewrap, and decoding
ten frames of a synthetic 360p video. All passed.

These checks show that programs start and find their libraries. They say
nothing about speed, touch, display or sandboxing on the phone. Those were
tested separately; see [test-results.md](test-results.md).

The rebuilt labwc, keyboard and Foot were also run together in a headless
session on the host, and text typed through the virtual keyboard reached the
terminal.

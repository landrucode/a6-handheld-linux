# Host scripts

None of these scripts write to the phone's storage, and none of them exploit
or reset the phone. Putting the phone into pwned DFU mode is a manual step.

## Main path

| Script | Purpose |
| --- | --- |
| `build-a6-handheld-from-source.py` | Builds the desktop and browser images from public inputs. |
| `check-a6-handheld-elf.py` | Starts the built ARM programs under QEMU user emulation as a quick check. |
| `build-a6-wifi-native.sh` | Builds the kernel and modules. Needs the private Apple inputs. |
| `build-host-loader.sh` | Builds the host boot loader from your checkm8_bootkit and libirecovery checkouts. |
| `manage-a6-ram-update.py` | Packs, signs, verifies and selects boot bundles. |
| `a6-boot-selected.py` | Boots the selected bundle on a phone already in pwned DFU mode. |
| `a6-usb-network-host.py` | Brings up the USB network link on the host (needs root). |
| `a6-provision-boot.py` | Sends the network bootstrap and starts image delivery. |
| `preflight.sh` | Reports host tools and connected Apple USB devices. |

[BUILDING.md](../BUILDING.md) shows how these fit together.

## Tests

The `test-*.py` scripts run on the host. They cover the Wi-Fi transport
parser, signed bundle handling and the generated desktop base, among other
things. Some need the pinned Linux `brcmfmac` source; see BUILDING.md.

## Bring-up tools

Most of the other scripts are probes and proof builds from bringing up the
hardware: boot handoff, SMP, USB, touch, audio, charger and Wi-Fi. They are
kept as a record and are not needed to build or boot the current system.
Read a script before running it on a phone.

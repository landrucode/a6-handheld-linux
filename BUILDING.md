# Building and booting

There are two separate parts:

1. **Desktop and browser images.** These build from public inputs alone.
2. **Kernel and boot images.** These need Apple files you extract yourself.

None of the commands here write to the phone's storage, reset it or run the
exploit.

## 1. Desktop and browser

### Host requirements

Python 3, git, curl, GPG, OpenSSL, ripgrep, make, GCC, Clang/LLVM/LLD, pkg-config,
`wayland-scanner`, `update-mime-database`, ffmpeg and ffprobe, plus the
development headers for SquashFS's compression libraries. Root is not needed.

### Build

From a fresh checkout:

```sh
python3 scripts/build-a6-handheld-from-source.py
```

The builder checks out the upstream revisions pinned in
`rootfs/handheld-build-sources.json`. It downloads the packages locked in
`rootfs/arch-*-packages.json` and checks their hashes and signatures. Package
install scripts are never run. It then builds the compiler sysroot, keyboard,
oomd, panel, audio stack, user tools, video test files, desktop and browser.

If the Arch Linux ARM mirrors no longer carry the locked packages, point the
builder at a directory of the original signed downloads. They are checked
again before use:

```sh
python3 scripts/build-a6-handheld-from-source.py \
  --package-cache /path/to/signed-package-downloads
```

### Output

- `build/handheld/desktop.squashfs`: labwc, Foot, keyboard, panel, PipeWire,
  user tools and mpv, with the pastel theme.
- `build/epiphany-runtime/browser.squashfs`: the browser.
- `build/handheld/desktop.source-build.json`: inputs, output hashes and sizes,
  and the result of each step. Logs are in `build/handheld/build-logs/`.

### Quick check

With `qemu-arm-static` or `qemu-arm` installed:

```sh
python3 scripts/check-a6-handheld-elf.py \
  --desktop-image build/handheld/desktop.squashfs \
  --browser-image build/epiphany-runtime/browser.squashfs
```

This starts the main ARM programs under user-mode emulation to check that they
run and find their libraries. It does not test the phone.

## 2. Kernel and boot images

The kernel is mainline Linux at `587858367581b9c55c3690f4e63382ad622719d4`
with the code in `kernel/`. Building a bootable image also needs these files
from Apple's iOS firmware for the iPhone5,2. None of them are in this
repository:

- iBSS and iBEC bootloaders, patched for pwned DFU
- the Apple device tree and kernelcache container
- Wi-Fi firmware and NVRAM
- touch controller firmware and calibration

The scripts were developed against the iOS 8.4.1 (12H321) bootloaders and
device tree, with some touch research also using an iOS 10 kernelcache. The
Wi-Fi firmware packing step (`scripts/prepare-a6-wifi-trx.py`) also needs a
checkout of [Project Cascadia](https://github.com/rzxvx/Project-Cascadia) in
`.deps/cascadia-wifi-reference`.

The boot scripts expect the bootloaders and device tree under
`.deps/legacy-ios-kit/firmware/`. The `extract-*`, `prepare-a6-*` and
`*-calibration` scripts in `scripts/` prepare the firmware and calibration
inputs. This release does not have a full step-by-step guide for that yet.

The kernel and boot scripts come from the development setup and have not yet
been run from a fresh checkout. Some still use older paths. For example,
`scripts/prepare-a6-boot-assets.py` (run by the kernel build) and
`a6-provision-boot.py` expect a desktop image at
`build/arch-bootstrap/arch-hyprland-user-desktop-native.squashfs`, which the
public desktop builder does not create. Expect to adjust paths.

### Private files

These live in your home directory, must be mode 600, and are never committed:

| File | Contents |
| --- | --- |
| `~/.a6-wifi.conf` | A `wpa_supplicant` configuration for your network. You create it. |
| `~/.a6-wifi-mac` | The phone's Wi-Fi MAC address. Created with a random local address if missing. |
| `~/.a6-usb-rpc.token` | Token for the USB root recovery channel. Created if missing. |
| `~/.a6-update-signing.key` | Ed25519 key that signs boot bundles. Created by `prepare-a6-boot-assets.py` if missing. |

The Wi-Fi regulatory country is set to GB in `scripts/prepare-a6-boot-assets.py`
and `rootfs/a6-wifi-boot.sh`. Change it to your own country before using
Wi-Fi.

With those in place, build the kernel and modules:

```sh
A6_WIFI_BOOT_DEFAULTS=1 A6_WIFI_HARDENING=1 A6_WIFI_BOOT_CPUS=2 \
  bash scripts/build-a6-wifi-native.sh
```

Run only one kernel build at a time; they share `.deps/linux`.

### Signed boot bundles

`scripts/manage-a6-ram-update.py` packs the kernel, modules, desktop and
browser into a signed bundle, checks it and selects it for the next boot.
Selecting a bundle only changes a pointer on the host.

```sh
python3 scripts/manage-a6-ram-update.py pack BUNDLE --browser --apps \
  --desktop-image build/handheld/desktop.squashfs \
  --browser-image build/epiphany-runtime/browser.squashfs
python3 scripts/manage-a6-ram-update.py verify BUNDLE
python3 scripts/manage-a6-ram-update.py apply BUNDLE
```

`--browser` also needs the time-sync runtime from
`scripts/prepare-a6-time-runtime.py`. `BUNDLE` is a directory under `build/signed-updates/`, for example
`build/signed-updates/my-bundle`. `--package-dir` and `--image` select a kernel
module package and kernel image other than the defaults.

### Host boot loader

The boot step needs two host tools:

- `build/host/checkm8-bootkit-linux`, built by `scripts/build-host-loader.sh`
  from your own checkouts of
  [checkm8_bootkit](https://github.com/NyanSatan/checkm8_bootkit) in
  `.deps/checkm8_bootkit` and libirecovery in `.deps/libirecovery`
- `irecovery` from [Legacy-iOS-Kit](https://github.com/LukeZGD/Legacy-iOS-Kit)
  at `.deps/legacy-ios-kit/bin/linux/x86_64/irecovery`

## 3. Booting the phone

Put the phone into pwned DFU mode first, with a checkm8 tool of your choice.
Then:

```sh
python3 scripts/a6-boot-selected.py --boot
sudo python3 scripts/a6-usb-network-host.py up
python3 scripts/a6-provision-boot.py --selected-update --browser --nts
```

1. `a6-boot-selected.py` checks the selected bundle, then loads iBSS, iBEC, the
   device tree and the kernel. Without `--boot`, it only checks and sends
   nothing.
2. `a6-usb-network-host.py` brings up the USB network link on the host.
3. `a6-provision-boot.py` sends the network bootstrap over USB. It sets up the
   firewall before the phone joins Wi-Fi, then fetches the large images over
   Wi-Fi. If DHCP or the gateway fails within 60 seconds, it uses paced USB
   instead. The phone checks hashes and signatures before starting the
   desktop.

## Host tests

The C test harnesses need one upstream file from the pinned Linux revision:

```sh
mkdir -p build .deps/linux/drivers/net/wireless/broadcom/brcm80211/brcmfmac
curl -fLsS https://raw.githubusercontent.com/torvalds/linux/587858367581b9c55c3690f4e63382ad622719d4/drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c \
  -o .deps/linux/drivers/net/wireless/broadcom/brcm80211/brcmfmac/usb.c
python3 scripts/test-a6-wifi-brcmfmac-hsic.py
python3 scripts/test-a6-wifi-rx-canonical.py
python3 scripts/test-a6-generated-desktop-base.py
python3 scripts/test-a6-ram-update.py
bash -n rootfs/a6-start-native-keyboard.sh rootfs/a6-start-user-labwc.sh
```

These test host code and bundle handling. Battery safety, radio behaviour and
touch can only be tested on the phone.

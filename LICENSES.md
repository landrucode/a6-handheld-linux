# Licences

The MIT licence in [LICENSE](LICENSE) covers this project's original code and
documentation. It does not relicense Linux, upstream patches or external
dependencies. Where a file has an SPDX header, the header applies.
`SOURCE-MANIFEST.json` lists every file with its hash.

| Material | Licence |
| --- | --- |
| Linux-derived code and patches | GPL-2.0, as in upstream Linux, or the file's own SPDX expression. |
| `kernel/font8x8.bin` | GPL-2.0. The 2048 bytes of font data from Linux `lib/fonts/font_8x8.c` at `587858367581b9c55c3690f4e63382ad622719d4` (SHA-256 `b8c58a575869ca4f1e8faf94cdd55781f89bdc1db64575d6ef38c4575bb04f0f`). The source and licence are in `third-party/linux/`. |
| `kernel/platform/brcmfmac-a6-hsic.h` | ISC, per its SPDX header. |
| `rootfs/aquamarine-*.patch` | Patches to Aquamarine (BSD-3-Clause); see `third-party/aquamarine/LICENSE`. |
| `scripts/patch-a6-ehci-trial.py` | Adapts an HSIC reset quirk from [Project Cascadia](https://github.com/rzxvx/Project-Cascadia) (GPL-2.0) at `00303679c33afcf2e59b26671b584a69a9718789`. `kernel/platform/a6-wifi-usb-download.inc` follows Cascadia's HSIC firmware download sequence. |
| wvkbd changes (`scripts/build-a6-wvkbd.sh`) | wvkbd is GPL-3.0, and builds with these changes stay GPL-3.0. |

This repository contains source only. It has no compiled phone images,
packages, Apple firmware or Apple calibration data. The touch matrix in
`rootfs/a6-touch-calibration.matrix` is this project's own fit. Arch Linux ARM packages carry
their own licences. Anyone redistributing built images needs to check
package licences and provide the corresponding source.

checkm8_bootkit has no top-level licence file. You check it out yourself; it
is not included here. Do not redistribute its compiled host binary.

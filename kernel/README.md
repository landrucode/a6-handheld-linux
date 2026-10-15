# Kernel

The kernel is mainline Linux at
`587858367581b9c55c3690f4e63382ad622719d4`, plus the code in this directory.
The upstream tree is not vendored. The build scripts check it out under
`.deps/linux`.

- `platform/`: A6 drivers and platform code, including the interrupt
  controller (`irq-apple-a6-aic.c`), timer, SMP, USB PHY, framebuffer, touch,
  audio, the D1972 PMU charger policy, and Wi-Fi HSIC support for `brcmfmac`.
  Files whose names include `probe`, `observe`, `capture` or `proof` are
  bring-up diagnostics. Despite its name, `ehci-a6-trial.c` is the HSIC host
  driver used for Wi-Fi.
- `patches/`: small changes to upstream drivers (DWC2 USB and the S5L UART).
- `a6-ram-root.config`: kernel configuration for the RAM-root system.
- `a6-minimal.config`: a small configuration from early bring-up.
- `font8x8.bin`: console font data from Linux (GPL-2.0).

Build with `scripts/build-a6-wifi-native.sh`; see [BUILDING.md](../BUILDING.md).

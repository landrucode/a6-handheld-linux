# Release notes

## 0.1.0 (2026-10-15): first public source release

The first public release of the source. The iPhone 5 (iPhone5,2) boots Linux
from RAM and runs a touch desktop: labwc, Foot, Epiphany, an on-screen keyboard
and an app panel. Touch, audio, Wi-Fi and charging work. Both CPU cores are in
use.

### Included

- Kernel platform code and patches for the A6: interrupt controller, timer,
  SMP, USB, touch, audio, charger and display.
- Wi-Fi support for the stock `brcmfmac` driver over this phone's HSIC link.
- A builder that makes the desktop and browser images from pinned public
  sources. Two clean builds gave identical output.
- Host tools for boot, provisioning and signed boot bundles.
- Hardware test results and a screenshot from the phone.

### Not included

Apple firmware and bootloaders, Apple's per-device calibration data,
compiled kernels or images, and the development history. The kernel build
needs Apple files you extract yourself; [BUILDING.md](BUILDING.md) lists them.

### Known problems

See [README.md](README.md#known-problems). In short: an unexplained overnight
discharge, Wi-Fi stalls that the health check recovers from, USB stalls on
large transfers, frame drops in video, and no suspend.

### Wi-Fi finding

On this phone, Wi-Fi data sent to the chip uses plain BDC framing, but data
coming back carries an extra 16-byte wrapper. The driver handles the two
directions differently. See
[docs/wifi-transport.md](docs/wifi-transport.md).

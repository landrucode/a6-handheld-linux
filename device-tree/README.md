# Device tree

Linux device trees for the iPhone5,2 (N42AP).

`a6-n42ap.dts` is the base tree. The other `.dts` files are variants used
during bring-up (USB console, full-speed USB, timer and SMP experiments).
`scripts/build-a6-zimage.sh` chooses one from its environment flags and
appends it to the kernel.

## Hardware map from the iOS device tree

Apple's own device tree (from iOS 8.4.1 build 12H321) is not a standard FDT.
It is read from the user's firmware on the host and is not included here.
The addresses below came from it.

The root identifies `N42AP`, `iPhone5,2` and `AppleARM`. The A6 `arm-io`
window uses child addresses translated through `ranges` from `0x00000000` to
physical `0x30000000`, with a `0x10000000` span. The main nodes for Linux are:

| Node | Child register range | Interrupt |
| --- | --- | --- |
| `arm-io/aic` | `0x0f200000 + 0x10000` | interrupt controller |
| `arm-io/gpio` | `0x0fa00000` | `0x77` |
| `arm-io/pmgr` | `0x0f100000 + 0x7000` and related ranges | timer/clock manager |
| `arm-io/wdt` | `0x0f103020` | `0x04` |
| `arm-io/uart1` | `0x02600000 + 0x1000` | `0x16` |
| `arm-io/i2c0` | `0x03200000` | `0x12` |
| `arm-io/usb-complex/usb-ehci` | `0x00300000 + 0x10000`, `0x00600000 + 0x10000` | `0x0c` |
| `arm-io/usb-complex/usb-ohci0` | `0x00400000` | `0x0d` |
| `arm-io/clcd` | `0x0a100000 + 0x7000`, `0x09200000 + 0x2000`, `0x09300000 + 0x1000` | `0x2a`, `0x2b` |

The USB ranges above are child offsets; applying the `arm-io` translation gives
physical bases beginning at `0x30300000` and `0x30600000`. The tree reports two
Swift ARMv7 CPUs and an AIC parent at `0x0f200000`. Its `memory` node is a zero
placeholder.

# Wi-Fi over HSIC

The iPhone 5's Broadcom Wi-Fi chip sits on an HSIC (inter-chip USB) link. With
the changes here, the stock Linux `brcmfmac` driver gives a normal network
interface: WPA2 association, DHCP and renewal, ARP, and two-way traffic all
work. The Wi-Fi firmware and board NVRAM come from your own iOS firmware and
are not included.

## Bring-up

A start-up script loads the firmware onto the chip and signals that it is
ready. Only then does the `brcmfmac` driver bind. The phone's chip is matched
by USB ID `0x0a5c:0xbd1a`. The patch adds:

- the firmware and chip mapping
- workarounds for control requests
- draining of the interrupt endpoint
- removal of the receive wrapper described below

Data transmit is off until the bring-up script has loaded the firewall rules.
The script then sets the country (GB in this build), turns off MPC (Broadcom's
minimum power consumption mode) and station power saving, and joins the
network. Turning the radio off restores the saved
settings and stops transmit. Wi-Fi credentials are read from a root-only file
in RAM and are never built into the driver or images.

## Receive and transmit use different framing

On USB, `brcmfmac` uses Broadcom's BCDC protocol: control messages carry a CDC
header and data frames a BDC header.

| Path | Framing |
| --- | --- |
| Control | Standard CDC control messages. |
| Receive | Each frame carries an extra 16-byte HSIC wrapper. The driver checks it and strips it, then hands the frame to normal BDC parsing. |
| Transmit | Plain BDC with no wrapper. Adding a 16-byte wrapper broke ARP and DHCP. |

The receive check covers the direction and type bits, the total length and a
16-bit folded checksum. Frames without a wrapper go straight to BDC parsing.

An early firmware loopback test was misleading. It sent back a fixed
1,856-byte block that included the transmitted bytes, even with a
deliberately wrong checksum. So it was copying the data, not checking it.
Tests with real network traffic showed how transmit framing works.

Host C tests (`scripts/test-a6-wifi-*.py`) cover cleanup, refill, framing
bounds and event parsing.

## Known fault: connected but no traffic

Sometimes the link stays associated but traffic stops. One occurrence was
recorded in detail:

- WPA was still connected, power saving was off and about 793 MiB of memory
  was free.
- Receive completions stopped at 71,245. All 50 receive requests were still
  queued, and no receive, allocation or submission errors were recorded.
- Transmit requests piled up while ARP and gateway pings failed.

This time the cause was not running out of receive buffers or memory. The
evidence does not yet separate a firmware fault, an HSIC scheduling problem or
a USB controller problem.

The health check (`rootfs/a6-wifi-health.sh`) saves the driver counters,
waits for three failed gateway checks, then restarts the HSIC interface. When
this fault happened during an image download, the restart brought DHCP and the
gateway back, and the download continued. This works around the fault; it
does not fix it.

## Source files

- `scripts/prepare-a6-brcmfmac-n42.py` and
  `scripts/prepare-a6-brcmfmac-diagnostics.py`: driver patches
- `kernel/platform/brcmfmac-a6-hsic.h`: HSIC framing
- `kernel/platform/ehci-a6-trial.c` and `kernel/platform/a6-wifi-usb-*.inc`:
  the HSIC host side and firmware download
- `rootfs/a6-wifi-boot.sh`, `rootfs/a6-wifi-recover.sh` and
  `rootfs/a6-wifi-health.sh`: bring-up, recovery and health check

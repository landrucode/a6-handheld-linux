# USB faults

USB carries the kernel, the network bootstrap and the root recovery channel.
Large images normally go over Wi-Fi instead, because of the fault below.

## Large transfers can stall

Large responses from the phone to the host can stall the USB Ethernet link
while the phone itself keeps running. Taking `usb0` down and up again brings
the link back. Some uploads to the phone have stalled too, but less often. The
cause is unknown; bulk-IN DMA, FIFO handling and completion handling are
candidates.

To reproduce it, serve a generated file of zeros from the phone's USB-only
HTTP server and fetch it from the host with `curl`, proxies off and a timeout
set. Record the bytes received, the time, host kernel messages and the phone's
USB counters before recovering the link.

When Wi-Fi fails and delivery falls back to USB, uploads go in 1 MiB windows
at 256 KiB/s. The `--usb-images` option of `a6-provision-boot.py` sends
everything over USB in 8 MiB windows at 1024 KiB/s by default. A partly
received file is checked before the upload resumes. Any old receiver is
stopped first so that two writers cannot collide.

## Faults that were in the tools

Two problems that looked like dead USB links were bugs in the host tools:

- **Missed completion markers.** When a marker was joined to the end of the
  previous output line, the reader missed it, and a command that had finished
  looked as if the link had died. Markers now start on a new line.
- **Rebind storm.** After a failed read, the host broker kept detaching and
  reclaiming the device every five seconds. It now claims the device once and
  records a fault until it is restarted by hand. Commands are never resent
  automatically when it is unclear whether they ran.

Fixing these did not remove the real fault: large transfers from the phone
still stall.

## Monitoring when USB drops

The root command channel listens only on the USB address and is protected by
a token and its own firewall rule. Checks from the Wi-Fi side found nothing
listening.

The phone keeps its own battery log in RAM from early boot, so the history
survives if the host stops reading. In one unplug and replug test it kept 446
samples over 3 h 43 min. The log is lost on reboot or if the battery runs flat.

This log could not explain the night the phone discharged; see
[test-results.md](test-results.md#power-and-battery).

Source files: `scripts/a6-provision-boot.py`, `scripts/a6-usb-acm-broker.py`,
`scripts/a6-usb-acm-direct.py`, `scripts/a6-usb-http-rpc.py`,
`rootfs/a6-usb-upload-recover.sh` and `rootfs/a6-power-longrun.sh`.

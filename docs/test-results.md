# Hardware test results

Results from the iPhone5,2 (N42AP) as of 2026-10-15. Each item was checked on
the phone unless it says otherwise. [STATUS.md](../STATUS.md) has the summary.

## Desktop

The current images were built from public sources (see
[source-rebuild.md](source-rebuild.md)), signed and booted on the phone. On
that boot:

- labwc, Foot, the keyboard, the panel and PipeWire started automatically.
- Typing, switching keyboard layouts, switching apps, and scrolling and
  pinch-zooming in Epiphany all worked by hand.
- Both PipeWire nodes appeared, and test tones played before and after the
  screen blanked and woke.
- The screen blanked after two minutes idle and woke on touch.
- `ping`, HTTPS, `ip`, `ss`, `ssh`, `htop` and `tmux` ran as user 1000.

Epiphany is the only browser shipped. It did better than Firefox in a
side-by-side test on the phone. Its web content process runs as user 1000 with
`no_new_privs`, seccomp mode 2, and its own user and mount namespaces.

## Security checks

- Desktop processes run as user 1000 with no capabilities and `no_new_privs`.
  There is no privilege escalation tool; root access is only over USB.
- The root recovery channel listens only on the USB address. Scans from the
  Wi-Fi side found no listener, and the firewall dropped unsolicited input.
- Replacing a bundle's signature with 64 zero bytes made the phone reject it.
  Restoring the signature made it pass again.

## Wi-Fi

- WPA2 association, DHCP, lease renewal, gateway pings and HTTPS all worked.
- A test with no storage involved echoed 256 MiB each way, verified byte for
  byte, in 137.4 seconds. A separate one-way receive of 256 MiB took 43.3
  seconds (without an end-to-end hash).
- A 100-minute workload run cycled through the browser, HTTPS, 30 seconds of
  360p H.264 video and the terminal every 15 minutes. It sent 201 uploads with
  no gateway failures.
- During one image download, the stall described in
  [wifi-transport.md](wifi-transport.md) happened naturally. The health check
  restarted the Wi-Fi interface after three failed gateway checks, DHCP came
  back, and the download resumed from where it stopped.
- Network time synchronised over NTS.

## Power and battery

- A phone-side power log kept 3006 samples over 25.08 hours with no gap over
  30.09 seconds, no charger faults and no low-battery trigger.
- With USB unplugged and replugged, the phone-side log kept 446 samples over
  3 h 43 min. The log is in RAM, so it survives USB loss but not a reboot or a
  flat battery.
- On one earlier night the host stopped receiving data and the phone was later
  found discharged. It is not known whether the kernel hung or only USB was
  lost. [charger-policy.md](charger-policy.md) explains what the charger code
  can and cannot do in that case.

## Video

In the workload run, mpv decoded 360p H.264 with no decoder drops but about
700 display drops, using about 145–150% CPU (out of 200% for two cores). The
bottleneck is software scaling and presentation, not decoding.

## Not tested

- Suspend to RAM. The kernel does not offer it, and screen blanking is not
  suspend.
- Whether screen blanking switches the backlight off.
- Long uninterrupted Wi-Fi use without the health check stepping in.

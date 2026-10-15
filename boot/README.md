# Boot

- `host/`: the Linux host loader. It uses the A6 payload from
  [checkm8_bootkit](https://github.com/NyanSatan/checkm8_bootkit) with the
  `libirecovery` backend. Build it with `scripts/build-host-loader.sh`.
  `probe` only reads the device state, `prepare` builds a command without
  sending it, and `boot` sends a bootloader image.
- `arm/`: ARM assembly for the Linux handoff (`linux-handoff.S`), the second
  CPU's start-up code (`a6-smp-secondary.S`), and probes used during bring-up.

The Linux kernel is a `zImage` with the N42AP device tree appended, wrapped in
the A6 kernelcache (Mach-O) format so that iBEC will start it.
`scripts/build-a6-kernelcache.sh` builds the wrapper. Its entry branch jumps
to the zImage, which decompresses Linux to `0x80008000`.

Compiled third-party binaries are never committed here.

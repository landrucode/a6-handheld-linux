# Root filesystem

Scripts, configuration and package locks for the phone's userspace.

- `arch-*-packages.json`: locked Arch Linux ARM package sets with hashes.
- `a6-start-*.sh`: start-up for the desktop, keyboard, apps and time sync.
- `a6-wifi-*.sh`, `a6-wifi.nft`: Wi-Fi bring-up, DHCP, health checks,
  recovery and firewall.
- `a6-labwc-panel.cpp`: the app panel, built by `scripts/build-a6-labwc-panel.sh`.
- `labwc/`: compositor configuration and autostart.

Files with `hyprland` in the name come from an earlier Hyprland desktop. The
start-up scripts can still launch it, but the image builder selects labwc, the
only desktop that is built and tested. The Aquamarine package lock is still
used to build the compiler sysroot.

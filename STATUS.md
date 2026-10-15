# Hardware status

Tested on an iPhone5,2 (N42AP). Last updated 2026-10-15.

| Area | Status |
| --- | --- |
| Boot | RAM only. Each cold boot needs a host computer and the phone in pwned DFU mode (checkm8). Nothing is written to the phone's storage. |
| CPU | Both Swift cores run Linux SMP. Cross-core TLB and cache maintenance were tested on hardware. |
| Memory | Compressed SquashFS images with a writable RAM overlay, plus zram swap. A userspace OOM killer (oomd) watches the browser. |
| Userspace | Arch Linux ARM (ARMv7). The desktop runs as user 1000 with no capabilities and `no_new_privs`. |
| Display | Software rendering through simpledrm and Pixman. Idle blanking after two minutes and wake on touch work. Blanking has not been shown to switch the backlight off. |
| Backlight | No driver yet, so brightness is fixed. |
| Touch | Native multitouch driver using the stock controller firmware. Calibration is a five-point fit and may need adjusting per device. |
| Keyboard | On-screen (wvkbd), shown automatically at boot. Typing has slight lag. |
| Audio | Speaker output and microphone input through ALSA and PipeWire. Playback works from a cold boot and after the screen wakes. |
| Wi-Fi | Stock `brcmfmac` over HSIC: WPA2, DHCP with lease renewal, two-way traffic. The firewall drops unsolicited input. See [known problems](README.md#known-problems) for the stall. |
| USB | Serial console, USB Ethernet and an authenticated root recovery channel that listens only on the cable. Large phone-to-host transfers can stall. |
| Charging | Automatic charging with voltage, temperature and current limits and a 3600 mV shutdown, on by default. Tested on wall chargers and computer ports. Experimental: see the [battery warning](README.md#known-problems). |
| Fuel gauge | Not working. Linux reads battery voltage, not percentage. |
| Time | NTS (authenticated NTP) over Wi-Fi. |
| Updates | Signed boot bundles are checked on the phone before startup. There is no persistent install. |
| Suspend | Not implemented. |
| Video | Software decoding works; display drops many frames. No hardware decoder driver. |
| GPU | Not supported. |
| Bluetooth, cellular, cameras, sensors, rotation, haptics | Not implemented. |

Test results are in [docs/test-results.md](docs/test-results.md).

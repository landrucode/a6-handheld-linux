#!/bin/bash
# Run in Foot as the desktop user. Detailed network/process output stays in RAM.
set -u
umask 077
[[ $(id -u) == 1000 && $(id -g) == 1000 ]] || exit 1
log=/home/a6/user-tools-check.private.log
: >"$log"
results=/home/a6/user-tools-check.results
: >"$results"
report() { printf "$@" | tee -a "$results"; }
check() {
 local label=$1
 shift
 if "$@" >>"$log" 2>&1; then
  report 'PASS %s\n' "$label"
 else
  report 'FAIL %s (details in %s)\n' "$label" "$log"
 fi
}
check 'UID 1000, no_new_privs' bash -c 'id; grep -Eq "^NoNewPrivs:[[:space:]]+1$" /proc/self/status'
check 'no privilege escalation commands' bash -c '! command -v sudo; ! command -v su; ! command -v doas'
gateway=$(ip -4 route show default dev wlan0 | awk 'NR==1 {print $3}')
if [[ -n "$gateway" ]]; then check 'ping gateway' ping -c3 -W3 "$gateway"; else report 'FAIL no Wi-Fi default route\n'; fi
check 'ip a' ip a
check 'ss -tuln' ss -tuln
check 'HTTPS certificate validation' curl --max-time 30 -I https://example.com
check 'ssh -V' ssh -V
check 'ps aux' ps aux
check 'htop installed' htop --version
check 'terminal definition' bash -c '[[ -n ${TERM:-} && -r /usr/share/terminfo/${TERM:0:1}/$TERM ]]'
if compgen -G '/sys/class/backlight/*/brightness' >/dev/null; then
 check 'brightnessctl set 50%' brightnessctl set 50%
else
 report 'BLOCKED brightness: kernel has no backlight class device\n'
fi
printf '\nOpening htop; press q to return to the shell.\n'
htop
exec bash

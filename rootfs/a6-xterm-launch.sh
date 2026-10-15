#!/bin/bash
export DISPLAY=:0 HOME=/root LANG=C PATH=/usr/bin:/bin
exec /usr/bin/xterm -geometry 80x80+0+0 -fn fixed -bg '#151b24' -fg '#f0f4fa' -title 'Arch Linux ARM on A6' -e /bin/bash --noprofile --norc -c 'printf "Arch Linux ARM on Apple A6\n\nReal Xorg + xterm running on the phone.\n\nBash %s\n" "$BASH_VERSION"; exec /bin/bash --noprofile --norc'

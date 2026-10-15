#!/bin/bash
set -euo pipefail
printf 'ARCH BASH %s\n' "$BASH_VERSION"
values=(apple a6 linux)
[[ ${#values[@]} == 3 && ${values[1]} == a6 ]]
[[ $(printf fork-ok) == fork-ok ]]
[[ $(printf '%s\n' pipeline | /bin/bash --noprofile --norc -c 'read -r value; [[ $value == pipeline ]] && printf pipeline-ok') == pipeline-ok ]]
/bin/bash --noprofile --norc -c 'exit 0' &
wait "$!"
seen=0
trap 'seen=1' USR1
kill -USR1 "$$"
[[ $seen == 1 ]]
[[ $EPOCHREALTIME == *.* ]]
printf 'ARCH ARRAYS FORK EXEC PIPE WAIT SIGNAL CLOCK PASS\n'

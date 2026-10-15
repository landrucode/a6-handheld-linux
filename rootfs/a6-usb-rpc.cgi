#!/bin/sh
# RAM-only, token-authenticated command path on the USB-bound HTTP server.
# The bearer token is in the POST body, never the URL or console.
if test "$1" != bounded; then
    exec /bin/busybox timeout 125 /bin/busybox sh "$0" bounded
fi
umask 077
reject() {
    printf 'Status: %s\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n\r\nRejected\n' "$1"
    exit 0
}
test "$REQUEST_METHOD" = POST && test "$REMOTE_ADDR" = 192.168.7.1 || reject '403 Forbidden'
case "$CONTENT_LENGTH" in ''|*[!0-9]*) reject '400 Bad Request';; esac
test "$CONTENT_LENGTH" -le 4096 && test "$CONTENT_LENGTH" -ge 67 || reject '400 Bad Request'
IFS= read -r token || reject '400 Bad Request'
expected=$(cat /tmp/a6-usb-rpc.token 2>/dev/null) || reject '403 Forbidden'
test "${#expected}" = 64 && test "$token" = "$expected" || reject '403 Forbidden'
IFS= read -r payload || reject '400 Bad Request'
command=$(printf '%s' "$payload" | /bin/busybox base64 -d 2>/dev/null) || reject '400 Bad Request'
test "${#command}" -ge 1 && test "${#command}" -le 2048 || reject '400 Bad Request'
printf 'Content-Type: text/plain\r\nCache-Control: no-store\r\n\r\n'
/bin/busybox timeout 120 /bin/busybox sh -c "$command" 2>&1
rc=$?
printf '\nA6_USB_RPC_RC=%s\n' "$rc"

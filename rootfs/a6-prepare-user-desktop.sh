#!/bin/bash
# Run as root inside the Arch RAM root, after seatd/uinput setup.
# Does not stop or launch a compositor. Does not modify host configuration.
set -euo pipefail
umask 022
[[ $(id -u) == 0 ]]
if grep -q '^a6:' /etc/passwd; then
    [[ $(id -u a6) == 1000 && $(id -g a6) == 1000 ]]
else
    ! grep -q '^[^:]*:[^:]*:1000:' /etc/passwd
    printf 'a6:!:1000:1000:A6 desktop:/home/a6:/bin/bash\n' >> /etc/passwd
fi
if ! grep -q '^a6:' /etc/group; then
    ! grep -q '^[^:]*:[^:]*:1000:' /etc/group
    printf 'a6:x:1000:\n' >> /etc/group
fi
[[ -S /run/seatd.sock && -c /dev/dri/card0 ]]
mkdir -p /home/a6/.config/foot /run/user/1000
install -m 644 /usr/local/share/a6/theme/foot.ini /home/a6/.config/foot/foot.ini
chown -R 1000:1000 /home/a6 /run/user/1000
chmod 755 / /home /run /run/user
chmod 700 /home/a6 /root /run/user/1000
chmod 1777 /tmp
chown 0:1000 /run/seatd.sock /dev/dri/card0
chmod 660 /run/seatd.sock /dev/dri/card0
# PTY allocation is available to users; each slave is owned by its creator.
/proc/1/root/bin/busybox mount -o remount,ptmxmode=0666,mode=0620 devpts /dev/pts
# The bootstrap base is files-only; normal user networking also needs DNS.
sed -i 's/^hosts:.*/hosts: files dns/' /etc/nsswitch.conf
# Generate server-auth anchors from the signed Mozilla trust package.
mkdir -p /etc/ssl/certs
trust extract --format=pem-bundle --filter=ca-anchors --purpose=server-auth --overwrite /etc/ssl/cert.pem
ln -sfn ../cert.pem /etc/ssl/certs/ca-certificates.crt
chmod 644 /etc/ssl/cert.pem
# Root grants only the desktop's ping group and backlight brightness file.
echo '1000 1000' >/proc/sys/net/ipv4/ping_group_range
for light in /proc/1/root/sys/class/backlight/*; do
 [[ -e "$light/brightness" ]] || continue
 chown 0:1000 "$light/brightness"
 chmod g+w "$light/brightness"
 # Keep the desktop sysfs read-only except this explicitly granted file.
 /proc/1/root/bin/busybox mount --bind "$light/brightness" "/sys/class/backlight/${light##*/}/brightness"
done
printf 'A6_USER_DESKTOP_PREPARED; launch with setpriv --nnp and UID1000\n'

/* RAM-only PID1: mount virtual filesystems, reap children, respawn USB ash. */
.syntax unified
.arch armv7-a
.arm
.section .text,"ax",%progbits
.global _start
_start:
    ldr r0, =devtmpfs
    ldr r1, =devdir
    bl mount_fs
    ldr r0, =procfs
    ldr r1, =procdir
    bl mount_fs
    ldr r0, =sysfs
    ldr r1, =sysdir
    bl mount_fs
#if A6_USB_NETWORK
    mov r7, #2
    svc #0
    cmp r0, #0
    beq network_child
    blt spawn
    mov r8, r0
network_wait:
    mov r0, r8
    mov r1, #0
    mov r2, #0
    mov r3, #0
    mov r7, #114
    svc #0
    cmn r0, #4
    beq network_wait
    b spawn
network_child:
    ldr r0, =busybox
    ldr r1, =network_argv
    ldr r2, =envp
    mov r7, #11
    svc #0
    b failed
#endif
spawn:
    mov r7, #2              /* fork */
    svc #0
    cmp r0, #0
    beq child
    blt retry
    mov r8, r0
reap:
    mvn r0, #0             /* wait4(-1), also reap adopted descendants */
    mov r1, #0
    mov r2, #0
    mov r3, #0
    mov r7, #114
    svc #0
    cmp r0, r8
    beq retry
    cmn r0, #10            /* ECHILD */
    bne reap
retry:
    ldr r0, =pause_time
    mov r1, #0
    mov r7, #162
    svc #0
    b spawn
child:
    mov r7, #66            /* setsid; child becomes terminal session leader */
    svc #0
    cmp r0, #0
    blt failed
    ldr r0, =port
    mov r1, #2             /* O_RDWR, blocking open until host connects */
    mov r2, #0
    mov r7, #5
    svc #0
    cmp r0, #0
    blt failed
    mov r8, r0
    movw r1, #0x540e       /* TIOCSCTTY */
    mov r2, #0
    mov r7, #54
    svc #0
    cmp r0, #0
    blt failed
    mov r9, #0
dup_loop:
    mov r0, r8
    mov r1, r9
    mov r7, #63            /* dup2 to stdin/out/err */
    svc #0
    cmp r0, #0
    blt failed
    add r9, r9, #1
    cmp r9, #3
    blt dup_loop
    cmp r8, #2
    ble exec_shell
    mov r0, r8
    mov r7, #6
    svc #0
exec_shell:
    ldr r0, =busybox
    ldr r1, =argv
    ldr r2, =envp
    mov r7, #11            /* execve busybox sh -i */
    svc #0
failed:
    mov r0, #127
    mov r7, #1             /* only child exits; PID1 remains */
    svc #0
    b failed
mount_fs:
    mov r2, r0
    mov r3, #0
    mov r4, #0
    mov r7, #21
    svc #0
    bx lr
.balign 4
pause_time: .word 1, 0
#if A6_USB_NETWORK
network_argv: .word shell, network_script, 0
network_script: .asciz "/etc/a6-network.sh"
.balign 4
#endif
argv: .word shell, interactive, 0
envp: .word path, home, term, prompt, 0
devtmpfs: .asciz "devtmpfs"
devdir: .asciz "/dev"
procfs: .asciz "proc"
procdir: .asciz "/proc"
sysfs: .asciz "sysfs"
sysdir: .asciz "/sys"
port: .asciz "/dev/ttyGS0"
busybox: .asciz "/bin/busybox"
shell: .asciz "sh"
interactive: .asciz "-i"
path: .asciz "PATH=/bin:/sbin"
home: .asciz "HOME=/"
term: .asciz "TERM=vt100"
prompt: .asciz "PS1=A6-RAM # "
.ltorg

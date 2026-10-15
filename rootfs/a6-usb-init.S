/* Volatile PID1 serial exerciser, not a shell. No disk access. */
.syntax unified
.arch armv7-a
.arm
.section .text,"ax",%progbits
.global _start
_start:
    ldr r0, =devtmpfs
    ldr r1, =devdir
    ldr r2, =devtmpfs
    mov r3, #0
    mov r4, #0
    mov r7, #21              /* mount devtmpfs */
    svc #0
open_port:
    ldr r0, =port
    mov r1, #2              /* O_RDWR, wait for host */
    mov r2, #0
    mov r7, #5
    svc #0
    cmp r0, #0
    bge opened
    ldr r0, =pause_time
    mov r1, #0
    mov r7, #162            /* nanosleep, avoid spinning */
    svc #0
    b open_port
opened:
    mov r8, r0
    ldr r2, =termios
    movw r1, #0x5401        /* TCGETS */
    mov r7, #54
    svc #0
    cmp r0, #0
    blt disconnected
    ldr r2, =termios
    mov r3, #0
    str r3, [r2]           /* raw input, output, local flags */
    str r3, [r2, #4]
    str r3, [r2, #12]
    strb r3, [r2, #22]     /* VTIME */
    mov r3, #1
    strb r3, [r2, #23]     /* VMIN: no local echo masquerading as PID1 */
    mov r0, r8
    movw r1, #0x5402        /* TCSETS */
    mov r7, #54
    svc #0
    cmp r0, #0
    blt disconnected
    mov r0, r8
    ldr r1, =banner
    ldr r2, =(banner_end-banner)
    bl write_all
read_loop:
    mov r0, r8
    ldr r1, =buffer
    mov r2, #256
    mov r7, #3
    svc #0
    cmp r0, #0
    ble disconnected
    mov r9, r0
    mov r0, r8
    ldr r1, =reply_prefix
    ldr r2, =(reply_prefix_end-reply_prefix)
    bl write_all
    mov r2, r9
    mov r0, r8
    ldr r1, =buffer
    bl write_all
    b read_loop
disconnected:
    mov r0, r8
    mov r7, #6
    svc #0
    ldr r0, =pause_time
    mov r1, #0
    mov r7, #162
    svc #0
    b open_port
write_all:
    push {r4, lr}
    mov r4, r0
1:  mov r0, r4
    mov r7, #4
    svc #0
    cmp r0, #0
    ble 2f
    add r1, r1, r0
    subs r2, r2, r0
    bne 1b
2:  pop {r4, pc}
.balign 4
pause_time: .word 1, 0
devtmpfs: .asciz "devtmpfs"
devdir: .asciz "/dev"
port: .asciz "/dev/ttyGS0"
banner: .ascii "\r\nA6 Linux PID 1: Lightning USB serial is alive.\r\nType a line; PID 1 will return it. This is not a shell.\r\n"
banner_end:
reply_prefix: .ascii "PID1 RX: "
reply_prefix_end:
.ltorg
.bss
.balign 4
buffer: .space 256
termios: .space 36

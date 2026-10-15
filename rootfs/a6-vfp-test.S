/* Static ARM hard-float probe: arithmetic, NEON, fork inheritance and
 * VFP register retention across repeated scheduler sleeps in two processes. */
.syntax unified
.arch armv7-a
.fpu neon-vfpv4
.eabi_attribute 28, 1
.arm
.text
.global _start
_start:
    ldr r0, =numbers
    vldr d0, [r0]
    vldr d1, [r0, #8]
    vadd.f64 d2, d0, d1
    vmov r0, r1, d2
    cmp r0, #0
    bne failed
    movw r2, #0
    movt r2, #0x4008  /* 3.0 double */
    cmp r1, r2
    bne failed
    vmov.i32 q0, #1
    vmov.i32 q1, #2
    vadd.i32 q0, q0, q1
    vmov r0, s0
    cmp r0, #3
    bne failed
    vmov r0, s3
    cmp r0, #3
    bne failed
    mov r8, #42
    vdup.32 q4, r8
    mov r7, #2
    svc #0
    cmp r0, #0
    blt failed
    mov r9, r0
    vmov r1, s16
    cmp r1, #42
    bne failed
    vmov r1, s19
    cmp r1, #42
    bne failed
    cmp r9, #0
    moveq r8, #17
    movne r8, #93
    vdup.32 q4, r8
    mov r10, #32
1:
    ldr r0, =pause
    mov r1, #0
    mov r7, #162
    svc #0
    cmp r0, #0
    bne failed
    vmov r0, s16
    cmp r0, r8
    bne failed
    vmov r0, s19
    cmp r0, r8
    bne failed
    subs r10, r10, #1
    bne 1b
    cmp r9, #0
    beq passed_child
    mov r0, r9
    ldr r1, =status
    mov r2, #0
    mov r3, #0
    mov r7, #114
    svc #0
    cmp r0, r9
    bne failed
    ldr r0, =status
    ldr r0, [r0]
    cmp r0, #0
    bne failed
    mov r0, #1
    ldr r1, =message
    ldr r2, =message_end-message
    mov r7, #4
    svc #0
passed_child:
    mov r0, #0
    b exit
failed:
    mov r0, #1
exit:
    mov r7, #1
    svc #0
    b exit
.balign 8
numbers: .word 0, 0x3ff00000, 0, 0x40000000
pause: .word 0, 1000000
message: .ascii "A6 VFP NEON FORK CONTEXT PASS\n"
message_end:
.bss
.balign 4
status: .space 4
.section .note.GNU-stack,"",%progbits

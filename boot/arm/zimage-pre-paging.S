/* Copy a terminal verifier into mapped kernel text at the call to paging_init. */
.syntax unified
.arch armv7-a
.thumb
#ifdef TRAMPOLINE_ONLY
#ifndef PROOF_ADDRESS
#error PROOF_ADDRESS is required
#endif
.section .text.boot, "ax", %progbits
.global _start
.type _start, %function
.thumb_func
_start:
    ldr.w pc, [pc, #0]
    .word (PROOF_ADDRESS + 1)
.size _start, . - _start
#else
.equ A6_SCRATCH, 0x83fff000
.equ COLOUR_WHITE, 0x00ffffff
.section .text.boot, "ax", %progbits
.global _start
.type _start, %function
.thumb_func
_start:
    ldr r0, =0x80008000
    cmp r4, r0
    bne rejected
    ldr r0, =0x80302ea4
    ldr r1, [r0]
    ldr r2, =0xfa8df001
    cmp r1, r2
    bne rejected
    ldr r1, [r0, #4]
    ldr r2, =0xfa06f505
    cmp r1, r2
    bne rejected
    ldr r2, =0x80300660
    adr r1, arm_stop
    ldr r3, =(arm_end - arm_stop)
copy_stop:
    ldr r12, [r1], #4
    str r12, [r2], #4
    subs r3, r3, #4
    bne copy_stop
    ldr r12, =0xf000f8df
    str r12, [r0]
    ldr r12, =0xc0300660
    str r12, [r0, #4]
    dsb sy
    mov.w r0, #0
    mov r1, r7
    mov r2, r8
    ldr r12, =0x82000a09
    bx r12
rejected:
    b rejected
    .ltorg
    .org 0x80
.arm
arm_stop:
    mrs r10, cpsr
    cpsid if
    ldr r3, =A6_SCRATCH
    ldr r8, =0x00ff0000
    mrc p15, 0, r11, c1, c0, 0
    tst r11, #1
    beq display
    adr r0, arm_stop
    ldr r11, =0xc0300660
    cmp r0, r11
    bne display
    ldr r11, =0xc0401fb8
    cmp sp, r11
    bne display
    ldr r8, =0x0000ffff
display:
    ldr r4, [r3]
    ldr r5, [r3, #4]
    ldr r6, [r3, #8]
    ldr r9, =COLOUR_WHITE
    mov r7, #0
row:
    mov r10, #0
    mov r2, r6, lsr #2
pixel:
    mov r11, r10, lsr #6
    eor r11, r11, r7, lsr #6
    tst r11, #1
    moveq r12, r8
    movne r12, r9
    str r12, [r4], #4
    subs r5, r5, #1
    beq done
    add r10, r10, #1
    subs r2, r2, #1
    bne pixel
    add r7, r7, #1
    b row
done:
    dsb sy
stop:
    wfe
    b stop
.ltorg
.balign 4
arm_end:
.size _start, . - _start
#endif

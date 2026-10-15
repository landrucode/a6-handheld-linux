/* Execute original LDR/STR/STR; verify the second scratch store. */
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
    ldr r1, [r4]
    ldr r2, =0xe59f3128
    cmp r1, r2
    bne rejected
    ldr r1, [r4, #4]
    ldr r2, =0xe5830010
    cmp r1, r2
    bne rejected
    ldr r1, [r4, #8]
    ldr r2, =0xe5831014
    cmp r1, r2
    bne rejected
    ldr r12, =(0xea000000 | ((0x80cbb960 - 0x80008014) >> 2))
    str r12, [r4, #0xc]
    ldr r0, =A6_SCRATCH
    mov.w r1, #0x5a5a5a5a
    str r1, [r0, #0x14]
    dsb sy
    mov.w r0, #0
    mov r1, r7
    mov r2, r8
    ldr r12, =0x82000a09
    bx r12
rejected:
    b rejected
    .ltorg
    .org 0x60
.arm
arm_stop:
    cpsid if
    ldr r0, =A6_SCRATCH
    ldr r4, [r0]
    ldr r5, [r0, #4]
    ldr r6, [r0, #8]
    ldr r12, [r0, #0x14]
    cmp r12, r1
    ldr r8, =0x00ff0000
    ldreq r8, =0x0000ffff
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
.size _start, . - _start
#endif

/* Copy a terminal verifier into mapped kernel text at first userspace write return-value classification with framebuffer preservation and mapped metadata snapshot. */
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
    ldr r0, =A6_SCRATCH
    adr r3, display_metadata
    ldr r1, [r0]
    ldr r2, =0xbf7aa000
    cmp r1, r2
    bne rejected
    str r1, [r3]
    ldr r1, [r0, #4]
    cmp r1, #0
    beq rejected
    cmp r1, #0x100000
    bhi rejected
    str r1, [r3, #4]
    ldr r1, [r0, #8]
    cmp r1, #0
    beq rejected
    tst r1, #3
    bne rejected
    cmp r1, #0x4000
    bhi rejected
    str r1, [r3, #8]
    ldr r0, =0x80100040
    ldrh r1, [r0]
    ldr r2, =0xb672
    cmp r1, r2
    bne rejected
    ldrh r1, [r0, #2]
    ldr r2, =0xf8d9
    cmp r1, r2
    bne rejected
    ldr r2, =0x80111df8
    adr r1, arm_stop
    ldr r3, =(arm_end - arm_stop)
copy_stop:
    ldr r12, [r1], #4
    str r12, [r2], #4
    subs r3, r3, #4
    bne copy_stop
    movw r12, #0xf8df
    strh r12, [r0]
    movw r12, #0xf000
    strh r12, [r0, #2]
    ldr r12, =0xc0111df8
    str r12, [r0, #4]
    ldr r0, =0x80304446
    ldrh r1, [r0]
    movw r2, #0xf6cb
    cmp r1, r2
    bne rejected
    ldrh r1, [r0, #2]
    movw r2, #0x7e60
    cmp r1, r2
    bne rejected
    movw r1, #0x7e40
    strh r1, [r0, #2]
    dsb sy
    mov.w r0, #0
    mov r1, r7
    mov r2, r8
    ldr r12, =0x82000a09
    bx r12
rejected:
    b rejected
    .ltorg
    .org 0x100
.arm
arm_stop:
    mrs r10, cpsr
    cpsid if
    adr r3, display_metadata
    ldr r8, =0x00ff0000
    cmp r7, #4
    bne display
    ldr r11, [sp, #68]
    ldr r12, =0x000200c8
    cmp r11, r12
    bne display
    cmp r0, #27
    beq full_write
    cmn r0, #9
    beq bad_fd
    cmp r0, #0
    blt other_error
    cmp r0, #27
    blo short_write
    ldr r8, =0x000000ff
    b display
full_write:
    ldr r8, =0x0000ffff
    b display
bad_fd:
    ldr r8, =0x00ff8000
    b display
other_error:
    ldr r8, =0x00ff00ff
    b display
short_write:
    ldr r8, =0x00ffff00
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
display_metadata:
    .word 0, 0, 0
arm_end:
.size _start, . - _start
#endif

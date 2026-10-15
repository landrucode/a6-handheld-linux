/* Copy a terminal verifier into mapped kernel text at console_device return with framebuffer preservation and mapped metadata snapshot. */
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
    ldr r0, =0x8019ebf0
    ldrh r1, [r0]
    ldr r2, =0x2800
    cmp r1, r2
    bne rejected
    ldrh r1, [r0, #2]
    ldr r2, =0xd042
    cmp r1, r2
    bne rejected
    ldr r2, =0x80111cf8
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
    ldr r12, =0xc0111cf8
    str r12, [r0, #4]
    /* Four-byte B.W hooks preserve adjacent branch targets. */
    ldr r0, =0x801b1806
    movw r1, #0xe92d
    ldrh r2, [r0]
    cmp r1, r2
    bne rejected
    movw r1, #0x4ff0
    ldrh r2, [r0, #2]
    cmp r1, r2
    bne rejected
    ldr r1, =entry_branch
    strh r1, [r0]
    lsr r1, r1, #16
    strh r1, [r0, #2]
    ldr r0, =0x801b1c1a
    movw r1, #0x4628
    ldrh r2, [r0]
    cmp r1, r2
    bne rejected
    movw r1, #0xb009
    ldrh r2, [r0, #2]
    cmp r1, r2
    bne rejected
    ldr r1, =return_branch
    strh r1, [r0]
    lsr r1, r1, #16
    strh r1, [r0, #2]
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
    .org 0x200
.arm
arm_stop:
    mrs r10, cpsr
    cpsid if
    adr r3, display_metadata
    adr r0, probe_record
    ldr r1, [r0]
    ldr r0, [r0, #4]
display:
    ldr r4, [r3]
    ldr r5, [r3, #4]
    ldr r6, [r3, #8]
    ldr r9, =COLOUR_WHITE
    mov r7, #0
row:
    /* Four 64-pixel bands repeated: entry, return, TTY pointer, errno bits. */
    mov r8, r7, lsr #6
    and r8, r8, #3
    cmp r8, #0
    bne return_band
    ldr r8, =0x00ff8000
    cmp r1, #0
    ldrne r8, =0x0000ffff
    b colour_ready
return_band:
    cmp r8, #1
    bne driver_band
    ldr r8, =0x00ff0000
    cmp r0, #0
    ldreq r8, =0x0000ff00
    cmp r0, #0x80000000
    ldreq r8, =0x00ff00ff
    b colour_ready
driver_band:
    cmp r8, #2
    bne binary_band
    ldr r8, =0xc04717bc
    ldr r8, [r8]
    cmp r8, #0
    ldreq r8, =0x00ff8000
    ldrne r8, =0x0000ffff
    b colour_ready
binary_band:
    mov r8, #0
colour_ready:
    mov r10, #0
    mov r2, r6, lsr #2
pixel:
    mov r11, r10, lsr #6
    eor r11, r11, r7, lsr #6
    tst r11, #1
    moveq r12, r8
    movne r12, r9
    /* Last band shows low 12 bits of absolute return, LSB at left. */
    and r11, r7, #192
    cmp r11, #192
    bne put_pixel
    rsb r11, r0, #0
    cmp r0, #0
    movge r11, r0
    mov r12, r10, lsr #5
    mov r11, r11, lsr r12
    tst r11, #1
    moveq r12, #0
    movne r12, r9
put_pixel:
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
.thumb
.balign 4
probe_enter:
    push.w {r4-r11, lr}
    push {r0-r2}
    mrs r2, apsr
    adr r0, probe_record
    ldr r1, [r0]
    add.w r1, r1, #1
    str r1, [r0]
    mov.w r1, #0x80000000
    str r1, [r0, #4]
    msr apsr_nzcvq, r2
    pop {r0-r2}
    ldr.w pc, entry_resume
.balign 4
entry_resume: .word 0xc01b180b
probe_return:
    push {r1}
    adr r1, probe_record
    str r5, [r1, #4]
    pop {r1}
    mov r0, r5
    add sp, #0x24
    ldr.w pc, return_resume
.balign 4
return_resume: .word 0xc01b1c1f
probe_record: .word 0, 0x80000000
.balign 4
display_metadata:
    .word 0, 0, 0
arm_end:
.equ entry_delta, (0xc0111cf8 + probe_enter - arm_stop) - 0xc01b180a
.equ return_delta, (0xc0111cf8 + probe_return - arm_stop) - 0xc01b1c1e
/* Both branches are backward by less than 4 MiB: S=I1=I2=J1=J2=1. */
.equ entry_branch, (0xf400 | ((entry_delta >> 12) & 0x3ff)) | ((0xb800 | ((entry_delta >> 1) & 0x7ff)) << 16)
.equ return_branch, (0xf400 | ((return_delta >> 12) & 0x3ff)) | ((0xb800 | ((return_delta >> 1) & 0x7ff)) << 16)
.size _start, . - _start
#endif

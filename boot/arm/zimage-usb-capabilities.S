/* USB capabilities and PHY handoff snapshot after proven gate enable.
 * 13 rows. Gate writes only, no core/PHY writes.
 * Green: accepted ID and stable paired reads with distinct UART seeds.
 * Cyan: unvalidated ID or paired-snapshot flags; red preflight; magenta timeout.
 */
.syntax unified
.arch armv7-a
.section .text.boot, "ax", %progbits
.global _start
.type _start, %function
.thumb
.thumb_func
_start:
#ifdef TRAMPOLINE_ONLY
    ldr.w pc, [pc, #0]
    .word (PROOF_ADDRESS + 1)
#else
    bx pc
    nop
.arm
    cpsid if
    mrc p15, 0, r0, c1, c0, 0
    tst r0, #1
    bne stop
    ldr r3, =0x83fff000
    ldr r4, [r3]
    ldr r2, =0xbf7aa000
    cmp r4, r2
    bne stop
    ldr r5, [r3, #4]
    cmp r5, #0
    beq stop
    cmp r5, #0x100000
    bhi stop
    ldr r6, [r3, #8]
    cmp r6, #0x800
    blo stop
    cmp r6, #0x4000
    bhi stop
    tst r6, #3
    bne stop
    mov r0, #0
    ldr r8, =0x00ff8000
    bl render
    adr r1, snapshot
    ldr r6, =0x32600004
    ldr r7, =0x32600010
    mov r8, #0
    /* Gate helper in stock iBEC: base 3f101000 + index * 4.
     * Each target is read after two different, non-destructive UART reads.
     * Store the first sample and flag any difference in the second sample.
     */
.macro gate_pair address, offset, flag
    ldr r2, =\address
    ldr r9, [r6]
    dsb sy
    ldr r4, [r2]
    dsb sy
    str r4, [r1, #\offset]
    ldr r10, [r7]
    dsb sy
    ldr r5, [r2]
    dsb sy
    cmp r9, r10
    orreq r8, r8, #16
    cmp r4, r5
    orrne r8, r8, #\flag
.endm
    gate_pair 0x3f101084, 0, 1
    gate_pair 0x3f101088, 4, 2
    gate_pair 0x3f10109c, 8, 4
    gate_pair 0x3f1010f8, 12, 8
    str r8, [r1, #16]
    cmp r8, #0
    bne preflight_fail
    ldr r3, [r1]
    cmp r3, #0x200
    bne preflight_fail
    ldr r3, [r1, #4]
    cmp r3, #0x200
    bne preflight_fail
    ldr r3, [r1, #8]
    cmp r3, #0x200
    bne preflight_fail
    ldr r3, [r1, #12]
    movw r4, #0x2ff
    cmp r3, r4
    bne preflight_fail
    /* Exact observed initial states required before any peripheral write.
     * Firmware order: parent UPERF, OTG, USBREG. Bounded polling.
     */
.macro enable_gate address, offset
    ldr r2, =\address
    ldr r3, [r2]
    orr r3, r3, #15
    str r3, [r2]
    dsb sy
    mov r4, #0x100000
1:
    ldr r3, [r2]
    and r5, r3, #255
    cmp r5, #255
    beq 2f
    subs r4, r4, #1
    bne 1b
    str r3, [r1, #\offset]
    b gate_timeout
2:
    str r3, [r1, #\offset]
.endm
    enable_gate 0x3f101084, 0
    enable_gate 0x3f101088, 4
    enable_gate 0x3f10109c, 8
    ldr r2, =0x36100040
    ldr r9, [r6]
    dsb sy
    ldr r4, [r2]
    dsb sy
    str r4, [r1, #12]
    ldr r10, [r7]
    dsb sy
    ldr r5, [r2]
    dsb sy
    str r5, [r1, #16]
    ldr r8, =0x0000ffff
    cmp r9, r10
    beq show
    cmp r4, r5
    bne show
    mov r3, r4, lsr #16
    movw r2, #0x4f54
    cmp r3, r2
    beq valid_id
    movw r2, #0x5531
    cmp r3, r2
    beq valid_id
    movw r2, #0x5532
    cmp r3, r2
    bne show
valid_id:
    adr r11, read_addresses
    mov r0, #0
    mov r8, #0
    mov r12, #1
read_next:
    ldr r2, [r11, r0, lsl #2]
    ldr r9, [r6]
    dsb sy
    ldr r4, [r2]
    dsb sy
    str r4, [r1, r0, lsl #2]
    ldr r10, [r7]
    dsb sy
    ldr r5, [r2]
    dsb sy
    cmp r9, r10
    orreq r8, r8, #0x10000
    cmp r4, r5
    orrne r8, r8, r12
    mov r12, r12, lsl #1
    add r0, r0, #1
    cmp r0, #12
    blo read_next
    str r8, [r1, #48]
    cmp r8, #0
    ldreq r8, =0x0000ff00
    ldrne r8, =0x0000ffff
    b show
preflight_fail:
    ldr r8, =0x00ff0000
    b show
gate_timeout:
    ldr r8, =0x00ff00ff
show:
    mov r0, #1
    bl render
stop:
    wfe
    b stop
render:
    ldr r3, =0x83fff000
    ldr r4, [r3]
    ldr r5, [r3, #4]
    ldr r6, [r3, #8]
    ldr r9, =0x00ffffff
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
    cmp r0, #0
    beq put_pixel
    mov r11, r7, lsr #6
    and r11, r11, #15
    cmp r11, #0
    beq put_pixel
    cmp r11, #13
    bhi put_pixel
    sub r11, r11, #1
    ldr r11, [r1, r11, lsl #2]
    mov r12, r10, lsr #4
    mov r11, r11, lsr r12
    tst r11, #1
    moveq r12, #0
    movne r12, r9
put_pixel:
    str r12, [r4], #4
    subs r5, r5, #1
    beq rendered
    add r10, r10, #1
    subs r2, r2, #1
    bne pixel
    add r7, r7, #1
    b row
rendered:
    dsb sy
    bx lr
.ltorg
.balign 4
read_addresses:
    .word 0x36100040, 0x36100044, 0x36100048, 0x3610004c
    .word 0x36100050, 0x36100e00, 0x36100010, 0x3610000c
    .word 0x36000000, 0x36000004, 0x36000008, 0x3600001c
snapshot:
    .space 52, 0
#endif
.size _start, . - _start

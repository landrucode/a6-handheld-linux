/* Enumeration proof: proven PHY startup, then bare-metal PIO EP0 handler.
 * 13 rows: stage, ID, PHY power/con/reset/UVLD, PCGCCTL, GRSTCTL,
 * GUSBCFG, GAHBCFG, GOTGCTL, DSTS, paired-read flags.
 * Green requires stage5 and flags0. Yellow: incomplete stage; cyan: flags.
 * Red gate preflight failure; magenta gate acknowledgement timeout.
 * No endpoint/FIFO/DMA setup or storage writes.
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
    ldr r1, =(0x80cbb900 + snapshot)
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
    ldr r2, =0x4f54272a
    cmp r4, r2
    bne phy_preflight_fail
    ldr r2, =0x36000000
    ldr r3, [r2]
    cmp r3, #0x1f
    bne phy_preflight_fail
    ldr r3, [r2, #4]
    cmp r3, #1
    bne phy_preflight_fail
    ldr r3, [r2, #8]
    cmp r3, #1
    bne phy_preflight_fail
    /* AIC counter and 24 ticks/us match iBEC1b40/1b70. */
    ldr r0, =240000
    bl delay_ticks
    cmp r0, #0
    beq timer_fail
    mov r0, #1
    bl set_stage
    ldr r2, =0x36100e00
    ldr r3, [r2]
    bic r3, r3, #3
    str r3, [r2]
    dsb sy
    ldr r0, =2400
    bl delay_ticks
    cmp r0, #0
    beq timer_fail
    ldr r2, =0x36000000
    mov r3, #0x200
    str r3, [r2, #0x60]
    mov r3, #6
    str r3, [r2]
    mov r3, #4
    str r3, [r2, #0x1c]
    movw r3, #0x749
    str r3, [r2, #0x40]
    movw r3, #0x2ff3
    str r3, [r2, #0x44]
    dsb sy
    mov r0, #240
    bl delay_ticks
    cmp r0, #0
    beq timer_fail
    ldr r2, =0x36000000
    ldr r3, [r2, #4]
    bic r3, r3, #3
    orr r3, r3, #1
    str r3, [r2, #4]
    ldr r3, [r2, #8]
    orr r3, r3, #1
    str r3, [r2, #8]
    dsb sy
    mov r0, #2
    bl set_stage
    mov r0, #480
    bl delay_ticks
    cmp r0, #0
    beq timer_fail
    ldr r2, =0x36000008
    ldr r3, [r2]
    bic r3, r3, #1
    str r3, [r2]
    dsb sy
    ldr r0, =24000
    bl delay_ticks
    cmp r0, #0
    beq timer_fail
    mov r0, #3
    bl set_stage
    ldr r2, =0x36100010
    mov r4, #0x1000000
wait_idle:
    ldr r3, [r2]
    tst r3, #0x80000000
    bne start_core_reset
    subs r4, r4, #1
    bne wait_idle
    mov r0, #0xe3
    b startup_failed
start_core_reset:
    orr r3, r3, #1
    str r3, [r2]
    dsb sy
    mov r0, #4
    bl set_stage
    ldr r2, =0x36100010
    mov r4, #0x1000000
wait_reset:
    ldr r3, [r2]
    tst r3, #1
    beq reset_cleared
    subs r4, r4, #1
    bne wait_reset
    mov r0, #0xe4
    b startup_failed
reset_cleared:
    mov r4, #0x1000000
wait_final_idle:
    ldr r3, [r2]
    tst r3, #0x80000000
    bne startup_success
    subs r4, r4, #1
    bne wait_final_idle
    mov r0, #0xe5
    b startup_failed
startup_success:
    mov r0, #5
    bl set_stage
    ldr sp, =0x80ccb900
    ldr pc, =0x80cbc901
phy_preflight_fail:
    mov r0, #0xe0
    b startup_failed
timer_fail:
    mov r0, #0xe1
startup_failed:
    bl set_stage
collect_snapshot:
    ldr r11, =(0x80cbb900 + read_addresses)
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
    ldrne r8, =0x0000ffff
    bne show
    ldr r3, [r1]
    cmp r3, #5
    ldreq r8, =0x0000ff00
    ldrne r8, =0x00ffff00
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
/* These leaf helpers preserve r1(snapshot), r6/r7(UART addresses). */
set_stage:
    ldr r2, =(0x80cbb900 + stage)
    str r0, [r2]
    bx lr
delay_ticks:
    ldr r2, =0x3f200020
    ldr r3, [r2]
    mov r5, #0x1000000
delay_loop:
    ldr r4, [r2]
    sub r4, r4, r3
    cmp r4, r0
    movhs r0, #1
    bxhs lr
    subs r5, r5, #1
    bne delay_loop
    mov r0, #0
    bx lr
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
    .word (0x80cbb900 + stage), 0x36100040, 0x36000000, 0x36000004
    .word 0x36000008, 0x3600001c, 0x36100e00, 0x36100010
    .word 0x3610000c, 0x36100008, 0x36100000, 0x36100808
stage:
    .word 0
snapshot:
    .space 52, 0
#endif
.size _start, . - _start

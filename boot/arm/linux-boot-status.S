/* Diagnostic only: persistent, bounded 3x8x8 text rows, one draw per stage.
 * Included into kernel head.S by the opt-in status build. Metadata comes
 * from the existing post-MMU snapshot, never from scratch after exec.
 */
.pushsection .text, "ax", %progbits
.thumb
.balign 4
.type a6_boot_draw, %function
.thumb_func
a6_boot_draw:
    cmp r0, #24
    bhs 9f
    ldr r1, =a6_boot_seen
    ldr r2, [r1]
    mov r3, #1
    lsl r3, r3, r0
    tst r2, r3
    bne 9f
    /* Reentry/IRQ-safe on this UP diagnostic: wrapper masks IRQ/FIQ. */
    orr r2, r2, r3
    str r2, [r1]
    ldr r1, =a6_fb_base_saved
    ldr r4, [r1]
    ldr r5, [r1, #8]       /* row bytes */
    ldr r6, [r1, #4]       /* pixel capacity */
    ldr r2, =0xbf7aa000
    cmp r4, r2
    bne 9f
    cmp r5, #2560          /* 640 visible pixels */
    blo 9f
    cmp r5, #0x4000
    bhi 9f
    tst r5, #3
    bne 9f
    cmp r6, #0x100000
    bhi 9f
    mov r2, #40
    mul r2, r0, r2
    add r2, r2, #80        /* reserve top 80px for early boot ledger */
    add r3, r2, #24
    mul r3, r5, r3
    lsl r6, r6, #2
    cmp r3, r6
    bhi 9f
    mul r2, r5, r2
    add r4, r4, r2
    add r4, r4, #32        /* left margin 8px */
    ldr r1, =a6_boot_labels
    ldr r7, [r1, r0, lsl #2]
    ldr r8, =a6_boot_font
    mov r9, #25           /* max 600 pixels, never beyond visible width */
1:  ldrb r0, [r7], #1
    cmp r0, #0
    beq 8f
    add r10, r8, r0, lsl #3
    mov r11, #0           /* glyph row */
2:  ldrb r0, [r10, r11]
    add r1, r11, r11, lsl #1
    mul r1, r5, r1
    add r1, r1, r4
    mov r12, #8
3:  mov r2, #0
    tst r0, #0x80
    it ne
    mvnne r2, #0xff000000 /* white or black */
    mov r3, r1
    /* Three identical scanlines and three pixels per glyph bit. */
    str r2, [r3]
    str r2, [r3, #4]
    str r2, [r3, #8]
    add r3, r3, r5
    str r2, [r3]
    str r2, [r3, #4]
    str r2, [r3, #8]
    add r3, r3, r5
    str r2, [r3]
    str r2, [r3, #4]
    str r2, [r3, #8]
    add r1, r1, #12
    lsl r0, r0, #1
    subs r12, r12, #1
    bne 3b
    add r11, r11, #1
    cmp r11, #8
    blo 2b
    add r4, r4, #96
    subs r9, r9, #1
    bne 1b
8:  dsb sy
9:  bx lr
.ltorg
.size a6_boot_draw, . - a6_boot_draw
.popsection

.pushsection .data, "aw", %progbits
.balign 4
a6_boot_seen: .word 0
.popsection

.pushsection .rodata, "a", %progbits
.balign 4
a6_boot_labels:
    .word 100f,101f,102f,103f,104f,105f,106f,107f
    .word 108f,109f,110f,111f,112f,113f,114f,115f
    .word 116f,117f,118f,119f,120f,121f,122f,123f
100: .asciz "00 MMU ON"
101: .asciz "01 START KERNEL"
102: .asciz "02 SETUP ARCH ENTER"
103: .asciz "03 CPU IDENTIFIED"
104: .asciz "04 DEVICE TREE OK"
105: .asciz "05 MEMBLOCK READY"
106: .asciz "06 PAGING ENTER"
107: .asciz "07 PAGE TABLE PREP OK"
108: .asciz "08 PAGING RETURNED"
109: .asciz "09 IRQS ENABLED"
110: .asciz "10 REST INIT ENTER"
111: .asciz "11 PID 1 RUNNING"
112: .asciz "12 DWC2 PROBE ENTER"
113: .asciz "13 PHY PROBE ENTER"
114: .asciz "14 PHY POWER ENTER"
115: .asciz "15 PHY POWER READY"
116: .asciz "16 DWC2 PARAMS ENTER"
117: .asciz "17 DWC2 UDC REGISTERED"
118: .asciz "18 SERIAL BIND ENTER"
119: .asciz "19 INITCALLS RETURNED"
120: .asciz "20 EXEC INIT ENTER"
121: .asciz "21 USERSPACE WRITE"
122: .asciz "22 UNDEFINED INSTRUCTION"
123: .asciz "23 MEMORY FAULT"
.balign 4
a6_boot_font:
/* Instrumenter appends the exact repository font using .incbin here. */

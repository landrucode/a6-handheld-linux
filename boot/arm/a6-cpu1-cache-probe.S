/* Private CPU1 MMU/D-cache transition and AIC IRQ; no Linux scheduler. */
.syntax unified
.arch armv7-a
.arm
.section .text.cpu1_tlbi, "ax", %progbits
.global a6_cpu1_tlbi_enter
.type a6_cpu1_tlbi_enter, %function
a6_cpu1_tlbi_enter:
    /* Caller has proven M/C/I off, private stacks, low vectors and PFR1. */
    ldr r2, =0x83ffe200
    mov r3, #20
    str r3, [r2]
    dsb sy
    mov r3, #0
    mcr p15, 0, r3, c2, c0, 2  /* TTBCR: TTBR0 for all addresses */
    ldr r3, =0x83ff8000
    mcr p15, 0, r3, c2, c0, 0  /* private aligned L1 */
    mov r3, #1
    mcr p15, 0, r3, c3, c0, 0  /* domain 0 client */
    mcr p15, 0, r3, c13, c0, 1 /* ASID 1 */
    mov r3, #0
    mcr p15, 0, r3, c8, c7, 0 /* local TLBIALL */
    dsb sy
    isb
#ifdef A6_CPU1_CACHE_TRE_PROBE
    /* Match CPU0's checked pinned ARMv7 remap registers before the
     * private table becomes active. No inherited CPU1 value is assumed.
     */
    ldr r3, =0xff0a81a8
    mcr p15, 0, r3, c10, c2, 0 /* PRRR */
    ldr r3, =0x40e040e0
    mcr p15, 0, r3, c10, c2, 1 /* NMRR */
    isb
    mrc p15, 0, r3, c10, c2, 0
    str r3, [r2, #96]
    ldr r0, =0xff0a81a8
    cmp r3, r0
    bne .Lremap_fail
    mrc p15, 0, r3, c10, c2, 1
    str r3, [r2, #100]
    ldr r0, =0x40e040e0
    cmp r3, r0
    bne .Lremap_fail
    mov r3, #23
    str r3, [r2]
    dsb sy
#endif
    /* Incoming C=0 was checked by the entry stub. Before enabling C,
     * invalidate this CPU's L1 D-cache by set/way as cache-v7.S does.
     * No other core's cache or AIC EVENT is touched.
     */
    b .Linvalidate_l1
.Lcache_return:
    ldr r2, =0x83ffe200
    mov r3, #22
    str r3, [r2]
    dsb sy
    mrc p15, 0, r3, c1, c0, 0
    orr r3, r3, #5            /* private MMU and D-cache on; I-cache off */
#ifdef A6_CPU1_CACHE_TRE_PROBE
    orr r3, r3, #0x10000000  /* use checked PRRR/NMRR with private table */
#endif
    mcr p15, 0, r3, c1, c0, 0
    dsb sy
    isb
    mrc p15, 0, r3, c1, c0, 0
    str r3, [r2, #68]
    mrc p15, 0, r3, c1, c0, 1 /* ACTLR read-only snapshot */
    str r3, [r2, #92]
    mov r3, #21
    str r3, [r2]
    dsb sy
    bx lr

#ifdef A6_CPU1_CACHE_TRE_PROBE
.Lremap_fail:
    mov r3, #253
    str r3, [r2]
    dsb sy
    b .Lpark
#endif

.Linvalidate_l1:
    mov r0, #0
    mcr p15, 2, r0, c0, c0, 0 /* CSSELR: L1 data/unified */
    isb
    mrc p15, 1, r0, c0, c0, 0 /* CCSIDR */
    movw r3, #0x3ff
    and r3, r3, r0, lsr #3
    clz r1, r3
    mov r2, #1
    mov r3, r3, lsl r1
    movs r1, r2, lsl r1
    moveq r1, #1
    and r2, r0, #7
    add r2, r2, #4
.Lcache_way:
    movw ip, #0x7fff
    and r0, ip, r0, lsr #13
.Lcache_set:
    mov ip, r0, lsl r2
    orr ip, ip, r3
    mcr p15, 0, ip, c7, c6, 2 /* DCISW */
    subs r0, r0, #1
    bpl .Lcache_set
    subs r3, r3, r1
    bcc .Lcache_done
    mrc p15, 1, r0, c0, c0, 0
    b .Lcache_way
.Lcache_done:
    dsb sy
    isb
    b .Lcache_return

.global a6_cpu1_tlbi_irq
a6_cpu1_tlbi_irq:
    stmdb sp!, {r0-r3, r12, lr}
    ldr r12, =0x3f202000
    ldr r0, [r12, #4]         /* receiving CPU's EVENT only */
    ldr r2, =0x83ffe200
    str r0, [r2, #32]
    mrs r1, spsr
    str r1, [r2, #36]
    mrs r1, cpsr
    str r1, [r2, #64]
    str lr, [r2, #40]
    ldr r1, =0x00040001
    cmp r0, r1
    bne .Lirq_fail
    mov r0, #1
    str r0, [r12, #0xc]       /* ACK OTHER */
    str r0, [r12, #0x28]      /* rearm OTHER */
    dsb sy
    ldr r1, [r2, #60]        /* 0: basic IPI; 5: read; 6: invalidate/read */
    cmp r1, #0
    beq .Lpublish
    cmp r1, #6
    bne .Lread
    ldr r3, =0xc0000000
    mcr p15, 0, r3, c7, c6, 1 /* DCIMVAC; CPU1 has only read the line */
    dsb sy
    isb
.Lread:
    ldr r3, =0xc0000000
    ldr r3, [r3]
    str r3, [r2, #56]
    dsb sy
.Lpublish:
    ldr r1, [r2, #28]
    add r1, r1, #1
    str r1, [r2, #28]
    mov r1, #4
    str r1, [r2]
    ldr r1, [r2, #52]
    dsb sy
    str r1, [r2, #48]
    dsb sy
    ldmia sp!, {r0-r3, r12, lr}
    subs pc, lr, #4
.Lirq_fail:
    mov r1, #1
    str r1, [r2, #44]
    mov r1, #255
    str r1, [r2]
    dsb sy
    b .Lpark

.global a6_cpu1_tlbi_abort
a6_cpu1_tlbi_abort:
    cpsid if
    ldr r2, =0x83ffe200
    mrc p15, 0, r3, c5, c0, 0 /* DFSR */
    str r3, [r2, #76]
    mrc p15, 0, r3, c6, c0, 0 /* DFAR */
    str r3, [r2, #80]
    mrs r3, spsr
    str r3, [r2, #84]
    str lr, [r2, #88]
    mov r3, #254
    str r3, [r2]
    dsb sy
.Lpark:
    wfe
    b .Lpark
.ltorg
.size a6_cpu1_tlbi_enter, . - a6_cpu1_tlbi_enter

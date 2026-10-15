/* Private CPU1 MMU transition and AIC IRQ; never enters Linux scheduler. */
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
    mrc p15, 0, r3, c1, c0, 0
    orr r3, r3, #1            /* MMU on; D/I caches remain off */
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
    ldr r1, [r2, #60]        /* 0: basic IPI; 1: read; 2/3/4: TLBI */
    cmp r1, #0
    beq .Lpublish
    cmp r1, #2
    bne .Lnot_page
    ldr r3, =0xc0000001     /* MVA plus test ASID */
    mcr p15, 0, r3, c8, c7, 1
    b .Lafter_tlbi
.Lnot_page:
    cmp r1, #3
    bne .Lnot_asid
    mov r3, #1
    mcr p15, 0, r3, c8, c7, 2
    b .Lafter_tlbi
.Lnot_asid:
    cmp r1, #4
    bne .Lread
    mov r3, #0
    mcr p15, 0, r3, c8, c7, 0
.Lafter_tlbi:
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

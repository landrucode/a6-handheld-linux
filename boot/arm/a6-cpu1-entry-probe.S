/* First contact only: no MMU transition or Linux tasks. The opt-in IPI variant
 * adds private exception stacks and receiving-CPU AIC reads.
 * Caller owns the code/marker page. Fail closed before RAM access unless
 * translation and both caches are disabled and virtualization is absent.
 */
.syntax unified
.arch armv7-a
.arm
#ifndef A6_CPU1_MARKER_PA
#error A6_CPU1_MARKER_PA must name a verified reserved physical page
#endif
#ifdef A6_CPU1_IPI_CHECKPOINTS
.macro checkpoint value
    mov r3, #\value
    str r3, [r2]
    dsb sy
.endm
#else
.macro checkpoint value
.endm
#endif
.section .text.cpu1_probe, "ax", %progbits
.global a6_cpu1_entry_probe
.type a6_cpu1_entry_probe, %function
a6_cpu1_entry_probe:
    cpsid if
    mrc p15, 0, r0, c1, c0, 0 /* incoming SCTLR */
    mrc p15, 0, r1, c0, c0, 5 /* MPIDR */
    mrs r4, cpsr
    mrc p15, 0, r5, c0, c0, 0 /* MIDR */
    mrc p15, 0, r6, c0, c1, 1 /* ID_PFR1 */
    movw r3, #0x1005            /* M, C, I */
    tst r0, r3
    bne .Lpark
#if defined(A6_CPU1_CACHE_PROBE) && !defined(A6_CPU1_CACHE_TRE_PROBE)
    tst r0, #0x10000000      /* TEX remap would change cache PTE meaning */
    bne .Lpark
#endif
    ubfx r3, r6, #12, #4       /* virtualization extension */
    cmp r3, #0
    bne .Lpark
#ifdef A6_CPU1_IPI_PROBE
    ubfx r3, r6, #4, #4        /* fixed-vector profile requires no Security Ext */
    cmp r3, #0
    bne .Lpark
#endif
    and r3, r1, #0xff
    cmp r3, #1
    bne .Lpark
    /* MMU-off nonvirtual data accesses are strongly ordered. No broad
     * maintenance of inherited cache contents, stack or C code here.
     */
    tst r4, #0x200            /* require current little-endian state */
    bne .Lpark
    ldr r2, =A6_CPU1_MARKER_PA
    ldr r3, =0xa6c10001
    str r3, [r2, #4]
    str r0, [r2, #8]
    str r1, [r2, #12]
    str r4, [r2, #16]
    str r5, [r2, #20]
    str r6, [r2, #24]
    dsb sy
    mov r3, #1
    str r3, [r2]
    dsb sy
    mov r3, #2                 /* initialized; entering WFE park */
    str r3, [r2]
    dsb sy
#ifdef A6_CPU1_TLBI_PROBE
.global a6_cpu1_tlbi_profile
.set a6_cpu1_tlbi_profile, 1
#endif
#ifdef A6_CPU1_CACHE_PROBE
.global a6_cpu1_cache_profile
.set a6_cpu1_cache_profile, 1
#endif
#ifdef A6_CPU1_IPI_PROBE
.global a6_cpu1_fixed_vectors
.set a6_cpu1_fixed_vectors, 1
    /* Known physical execution, private exception stacks and ARM vectors. */
    cps #0x12
    ldr sp, =0x83ffef00
    cps #0x13
    ldr sp, =0x83ffed00
#ifdef A6_CPU1_TLBI_PROBE
    cps #0x17                 /* private abort stack */
    ldr sp, =0x83ffec00
    cps #0x13
#endif
    checkpoint 10             /* private banked stacks established */
    bic r7, r0, #0x2000        /* low vectors through VBAR */
    bic r7, r7, #0x40000000    /* ARM exception entry */
    bic r7, r7, #0x02000000    /* little-endian exceptions */
    mcr p15, 0, r7, c1, c0, 0
#ifdef A6_CPU1_IPI_CHECKPOINTS
    isb
#endif
    checkpoint 11             /* SCTLR write completed */
    /* PFR1.Security=0: no VBAR. SCTLR.V=0 selects fixed physical zero. */
    dsb sy
    isb
    checkpoint 12             /* fixed low-vector selection synchronized */
#ifdef A6_CPU1_TLBI_PROBE
    ldr r7, =0x83ffd000
    blx r7                    /* returns only after private identity MMU on */
#endif
    ldr r12, =0x3f202000       /* current CPU's AIC register window */
    ldr r3, =0x80000001
    str r3, [r12, #0x24]      /* mask SELF and OTHER */
    checkpoint 13             /* mask write and full barrier completed */
    ldr r3, =0x80000001        /* checkpoint clobbers r3 */
    str r3, [r12, #0xc]       /* clear stale pending SELF and OTHER */
    checkpoint 14             /* ACK write and full barrier completed */
    mov r3, #1
    str r3, [r12, #0x28]      /* enable only OTHER */
    dsb sy
    checkpoint 15             /* OTHER unmask and barrier completed */
    cpsie i                   /* FIQ stays masked */
    mov r3, #3
    str r3, [r2]
    dsb sy
#endif
.global a6_cpu1_probe_park
a6_cpu1_probe_park:
.Lpark:
    wfe
    b .Lpark
#if defined(A6_CPU1_IPI_PROBE) && !defined(A6_CPU1_TLBI_PROBE)
.global a6_cpu1_probe_irq
a6_cpu1_probe_irq:
    stmdb sp!, {r0-r3, r12, lr}
    ldr r12, =0x3f202000
    ldr r0, [r12, #4]         /* EVENT on receiving CPU only */
    ldr r2, =A6_CPU1_MARKER_PA
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
    str r0, [r12, #0x28]      /* rearm OTHER after automatic mask */
    dsb sy
    ldr r1, [r2, #28]
    add r1, r1, #1
    str r1, [r2, #28]
    mov r1, #4
    str r1, [r2]
    ldr r1, [r2, #52]         /* CPU0's current challenge */
    dsb sy
    str r1, [r2, #48]         /* publish only after hardware ACK/rearm */
    dsb sy
    ldmia sp!, {r0-r3, r12, lr}
    subs pc, lr, #4
.Lirq_fail:
    mov r1, #1
    str r1, [r2, #44]
    mov r1, #255
    str r1, [r2]
    dsb sy
    b .Lpark                  /* IRQ remains masked; do not loop handlers */
#endif
.ltorg
.size a6_cpu1_entry_probe, . - a6_cpu1_entry_probe

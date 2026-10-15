/* SPDX-License-Identifier: GPL-2.0-only */
/* Owned MMU-off entry. No VBAR, WFI, Linux stack or cache assumption. */
#include "a6-smp-layout.h"
.syntax unified
.arch armv7-a
.arm
.section .text.a6_smp_bridge, "ax", %progbits
.global a6_smp_bridge
.type a6_smp_bridge, %function
a6_smp_bridge:
    cpsid if
    mrc p15, 0, r0, c1, c0, 0
    mrc p15, 0, r1, c0, c0, 5
    mrs r4, cpsr
    mrc p15, 0, r5, c0, c0, 0
    mrc p15, 0, r6, c0, c1, 1
    movw r3, #0x1005
    tst r0, r3                 /* MMU and I/D caches must be off */
    bne .Lpark
    and r3, r1, #0xff
    cmp r3, #1
    bne .Lpark
    ubfx r3, r6, #4, #4        /* no Security Ext: fixed vectors */
    cmp r3, #0
    bne .Lpark
    ubfx r3, r6, #12, #4       /* no virtualization extension */
    cmp r3, #0
    bne .Lpark
    tst r4, #0x200             /* little endian */
    bne .Lpark
    ldr r2, =A6_SMP_MARKER_PA
    ldr r3, =A6_SMP_MAGIC
    str r3, [r2, #A6_SMP_SIGNATURE]
    str r0, [r2, #A6_SMP_ENTRY_SCTLR]
    str r1, [r2, #A6_SMP_MPIDR]
    str r4, [r2, #A6_SMP_CPSR]
    str r5, [r2, #A6_SMP_MIDR]
    str r6, [r2, #A6_SMP_PFR1]
    mov r3, #A6_SMP_STAGE_ENTRY
    dsb sy
    str r3, [r2, #A6_SMP_STAGE]
    /* Fixed low vectors remain valid through the MMU-off handoff. */
    cps #0x13
    bic r0, r0, #0x2000
    bic r0, r0, #0x40000000
    bic r0, r0, #0x02000000
    mcr p15, 0, r0, c1, c0, 0
    isb
    ldr r7, [r2, #A6_SMP_SHADOW_PA]
    mov r8, #0
.Lcompare:
    ldr r0, [r7, r8]
    add r9, r2, #A6_SMP_OBSERVED_DATA
    str r0, [r9, r8]
    add r9, r2, #A6_SMP_EXPECT_DATA
    ldr r1, [r9, r8]
    cmp r0, r1
    bne .Lbad_data
    add r8, r8, #4
    cmp r8, #20
    blo .Lcompare
    mov r3, #A6_SMP_STAGE_READY
    dsb sy
    str r3, [r2, #A6_SMP_STAGE]
    dsb sy
    /* Bounded awake GO wait; a timeout parks in the proven WFE loop. */
    ldr r1, =A6_SMP_GO_MAGIC
    mov r8, #0x1000000
.Lwait:
    ldr r0, [r2, #A6_SMP_GO]
    cmp r0, r1
    beq .Lgo
    cmp r0, #0                 /* zero revokes permission */
    beq .Lpark
    subs r8, r8, #1
    beq .Lpark
    yield
    b .Lwait
.Lgo:
    ldr r3, [r2, #A6_SMP_TARGET]
    tst r3, #3                 /* branch to the ARM veneer, not Thumb */
    bne .Lbad_data
    mov r0, #A6_SMP_STAGE_BRANCH
    dsb sy
    str r0, [r2, #A6_SMP_STAGE]
    dsb sy
    bx r3
.Lbad_data:
    mov r0, #A6_SMP_STAGE_DATA_BAD
    str r0, [r2, #A6_SMP_STAGE]
    dsb sy
.global a6_smp_bridge_park
a6_smp_bridge_park:
.Lpark:
    cpsid if
    wfe
    b .Lpark
/* Only installed after the checked MMU-off entry; no exception stack. */
.global a6_smp_bridge_exception
a6_smp_bridge_exception:
    cpsid if
    ldr r2, =A6_SMP_MARKER_PA
    mrs r0, cpsr
    str r0, [r2, #A6_SMP_EXCEPTION]
    mov r0, #A6_SMP_STAGE_EXCEPTION
    str r0, [r2, #A6_SMP_STAGE]
    dsb sy
    b .Lpark
.ltorg
.size a6_smp_bridge, . - a6_smp_bridge

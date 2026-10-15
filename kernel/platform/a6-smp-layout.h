/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef A6_SMP_LAYOUT_H
#define A6_SMP_LAYOUT_H

#define A6_SMP_VECTOR_PA      0x80000000
#define A6_SMP_CODE_PA        0x83ffe000
#define A6_SMP_MARKER_PA      0x83ffe200
#define A6_SMP_MAGIC          0xa6c20001
#define A6_SMP_GO_MAGIC       0xa6c2beef

/* Physical, uncached marker words shared by the bridge and Linux. */
#define A6_SMP_STAGE          0x00
#define A6_SMP_SIGNATURE      0x04
#define A6_SMP_ENTRY_SCTLR    0x08
#define A6_SMP_MPIDR          0x0c
#define A6_SMP_CPSR           0x10
#define A6_SMP_MIDR           0x14
#define A6_SMP_PFR1           0x18
#define A6_SMP_GO             0x1c
#define A6_SMP_TARGET         0x20
#define A6_SMP_SHADOW_PA      0x24
#define A6_SMP_EXPECT_DATA    0x28 /* 5 u32: pgdir, swapper, stack, task */
#define A6_SMP_OBSERVED_DATA  0x40 /* same 5 words read by CPU1 */
#define A6_SMP_KERNEL_SCTLR   0x60
#define A6_SMP_KERNEL_PRRR    0x64
#define A6_SMP_KERNEL_NMRR    0x68
#define A6_SMP_KERNEL_CNTFRQ  0x6c
#define A6_SMP_COUNTER0       0x70
#define A6_SMP_COUNTER1       0x78
#define A6_SMP_RESULT         0x80
#define A6_SMP_EXCEPTION      0x84
#define A6_SMP_TIMER_READY    0x88
#define A6_SMP_KERNEL_TTBR0        0x90
#define A6_SMP_KERNEL_TTBR1        0x94
#define A6_SMP_KERNEL_TTBCR        0x98
#define A6_SMP_KERNEL_DACR         0x9c
#define A6_SMP_KERNEL_CONTEXTIDR   0xa0
#define A6_SMP_KERNEL_PC           0xa4
#define A6_SMP_KERNEL_SP           0xa8
#define A6_SMP_KERNEL_CPSR         0xac
#define A6_SMP_KERNEL_TIMER_CTL    0xb0


#define A6_SMP_STAGE_ENTRY       1
#define A6_SMP_STAGE_READY       2
#define A6_SMP_STAGE_BRANCH      3
#define A6_SMP_STAGE_KERNEL      4
#define A6_SMP_STAGE_QUARANTINED  5
#define A6_SMP_STAGE_DATA_BAD    0xf1
#define A6_SMP_STAGE_EXCEPTION   0xf2
#define A6_SMP_STAGE_KERNEL_BAD  0xf3
#define A6_SMP_STAGE_CANCELLED   0xf4

#endif

/*
 * Volatile A6 handoff liveness payload.
 *
 * This image deliberately performs no device or memory-mapped I/O.  If the
 * BOOT_DIAGS handoff reaches it, the CPU remains in this loop and the phone
 * should stop presenting a USB bootloader interface until it is restarted.
 */

.syntax unified
.arch armv7-a
.arm

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function

_start:
	/* BOOT_DIAGS enters the IMG3 payload at its ARM vector table. */
	b	1f
	b	1f
	b	1f
	b	1f
	b	1f
	b	1f
	b	1f
	b	1f

1:
	/* Keep the first instruction after the vectors mode independent. */
	b	1b

.size _start, . - _start

/*
 * Volatile A6 direct-execution proof payload.
 *
 * This is deliberately a diagnostic image, not a Linux loader.  It writes a
 * small red marker into the framebuffer address used by the A6 iBEC/display
 * path and then waits forever.  The address is a candidate derived from the
 * iBEC image and the documented iPhone 5 display map; it must be verified on
 * the N42AP device before this image is sent.
 */

.syntax unified
.arch armv7-a
.arm

.equ FRAMEBUFFER, 0xbf7aa000
.equ SCREEN_STRIDE, 4544          /* 1136 pixels * 4 bytes */
.equ MARKER_SIZE, 64
.equ MARKER_COLOR, 0x00ff0000     /* red in the usual 32-bit framebuffer */

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
	/* Do not allow an interrupt to divert the diagnostic loop. */
	cpsid   if

	ldr     r4, =FRAMEBUFFER
	ldr     r3, =MARKER_COLOR
	mov     r5, #0

1:
	mov     r2, #0
2:
	str     r3, [r4, r2, lsl #2]
	add     r2, r2, #1
	cmp     r2, #MARKER_SIZE
	blo     2b

	add     r4, r4, #SCREEN_STRIDE
	add     r5, r5, #1
	cmp     r5, #MARKER_SIZE
	blo     1b

3:
	wfe
	b       3b

.ltorg
.size _start, . - _start

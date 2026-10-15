/*
 * A6 relocated-zImage entry proof.
 *
 * The normal Linux handoff records the live framebuffer description at
 * 0x83fff000 before copying and entering the zImage.  This routine is reached
 * only by a branch installed at the relocated zImage's first instruction.  It
 * paints persistent horizontal stripes and stops without entering the normal
 * decompressor prologue.
 */

.syntax unified
.arch armv7-a
.arm

.equ A6_SCRATCH,   0x83fff000
.equ COLOUR_CYAN,  0x0000ffff
.equ COLOUR_YELLOW, 0x00ffff00

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function

_start:
	cpsid	if
	ldr	r0, =A6_SCRATCH
	ldr	r4, [r0]                  /* framebuffer base */
	ldr	r5, [r0, #4]              /* complete framebuffer word count */
	ldr	r6, [r0, #8]              /* row stride in bytes */
	cmp	r4, #0
	beq	stop
	cmp	r5, #0
	beq	stop
	cmp	r6, #0
	beq	stop
	cmp	r6, #8192
	bhi	stop
	tst	r6, #3
	bne	stop
	mov	r6, r6, lsr #2           /* words per row */

	ldr	r8, =COLOUR_CYAN
	ldr	r9, =COLOUR_YELLOW
	mov	r7, #0                    /* row number */

row:
	tst	r7, #64                   /* alternating 64-row bands */
	moveq	r3, r8
	movne	r3, r9
	mov	r1, r6
	cmp	r1, r5
	movhi	r1, r5
pixel:
	str	r3, [r4], #4
	subs	r5, r5, #1
	beq	done
	subs	r1, r1, #1
	bne	pixel
	add	r7, r7, #1
	b	row

done:
	dsb	sy
stop:
	wfe
	b	stop

.ltorg
.size _start, . - _start

/*
 * A6 kernel-entry launch proof.
 *
 * Entry follows the public XNU ARM contract: r0 points to boot_args.  Paint a
 * persistent, unmistakable striped framebuffer and stop.  This deliberately
 * performs no cache/MMU transition and never enters either XNU or Linux.
 */

.syntax unified
.arch armv7-a
.arm

.equ VIDEO_BASE,      0x14
.equ VIDEO_ROW_BYTES, 0x1c
.equ VIDEO_WIDTH,     0x20
.equ VIDEO_HEIGHT,    0x24
.equ COLOUR_MAGENTA,  0x00ff00ff
.equ COLOUR_WHITE,    0x00ffffff
.equ STRIPE_SHIFT,    6              /* 64-pixel vertical stripes */

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function

_start:
	cpsid	if
	mov	r11, r0

	/* Read Boot_Video from the boot_args supplied at kernel entry. */
	ldr	r4, [r11, #VIDEO_BASE]
	ldr	r5, [r11, #VIDEO_ROW_BYTES]
	ldr	r6, [r11, #VIDEO_WIDTH]
	ldr	r7, [r11, #VIDEO_HEIGHT]

	/* Refuse malformed dimensions rather than writing an inferred address. */
	cmp	r4, #0
	beq	stop
	cmp	r5, #0
	beq	stop
	cmp	r5, #8192
	bhi	stop
	cmp	r6, #0
	beq	stop
	cmp	r6, #2048
	bhi	stop
	cmp	r7, #0
	beq	stop
	cmp	r7, #4096
	bhi	stop
	mov	r0, r6, lsl #2
	cmp	r0, r5
	bhi	stop

	ldr	r8, =COLOUR_MAGENTA
	ldr	r9, =COLOUR_WHITE
	mov	r10, #0                    /* y */

row:
	mov	r0, r4                    /* pixel address */
	mov	r1, #0                    /* x */
pixel:
	mov	r2, r1, lsr #STRIPE_SHIFT
	tst	r2, #1
	streq	r8, [r0], #4
	strne	r9, [r0], #4
	add	r1, r1, #1
	cmp	r1, r6
	blo	pixel
	add	r4, r4, r5
	add	r10, r10, #1
	cmp	r10, r7
	blo	row
	dsb	sy

stop:
	wfe
	b	stop

.ltorg
.size _start, . - _start

/* Stop proof for the first instruction of the decompressed ARM Image. */

.syntax unified
.arch armv7-a
.arm

.equ A6_SCRATCH, 0x83fff000
.equ COLOUR_PRIMARY, 0x00ff8000
.equ COLOUR_WHITE,   0x00ffffff

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function

_start:
	cpsid	if
	ldr	r0, =A6_SCRATCH
	ldr	r4, [r0]
	ldr	r5, [r0, #4]
	ldr	r6, [r0, #8]
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
	mov	r6, r6, lsr #2

	ldr	r8, =COLOUR_PRIMARY
	ldr	r9, =COLOUR_WHITE
	mov	r7, #0

row:
	mov	r10, #0
	mov	r2, r6
	cmp	r2, r5
	movhi	r2, r5
pixel:
	mov	r11, r10, lsr #6
	eor	r11, r11, r7, lsr #6
	tst	r11, #1
	moveq	r12, r8
	movne	r12, r9
	str	r12, [r4], #4
	subs	r5, r5, #1
	beq	done
	add	r10, r10, #1
	subs	r2, r2, #1
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

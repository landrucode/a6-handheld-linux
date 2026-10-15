/* Read-only validation of the live kernel branch destination. */

.syntax unified
.arch armv7-a
.thumb

#ifdef TRAMPOLINE_ONLY
#ifndef PROOF_ADDRESS
#error PROOF_ADDRESS is required
#endif
.section .text.boot, "ax", %progbits
.global _start
.type _start, %function
.thumb_func
_start:
	ldr.w	pc, [pc, #0]
	.word	(PROOF_ADDRESS + 1)
.size _start, . - _start
#else
.equ A6_SCRATCH,  0x83fff000
#ifndef PROOF_COLOUR
#define PROOF_COLOUR 0x000000ff
#endif
.equ COLOUR_PRIMARY, PROOF_COLOUR
.equ COLOUR_WHITE, 0x00ffffff

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function
.thumb_func
_start:
	cpsid	if
	ldr	r12, =0x00ff0000
	ldr	r0, =0x80008000
	cmp	r4, r0
	bne	paint
	ldr	r1, [r4]
	ldr	r2, =0xe59f3128
	cmp	r1, r2
	bne	paint
	ldr	r12, =0x00ff00ff
paint:
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
	cmp.w	r6, #8192
	bhi	stop
	tst	r6, #3
	bne	stop
	lsrs	r6, r6, #2
	mov	r8, r12
	ldr	r9, =COLOUR_WHITE
	movs	r7, #0
row:
	movs	r1, #0
	mov	r2, r6
	cmp	r2, r5
	it	hi
	movhi	r2, r5
pixel:
	lsr.w	r10, r1, #6
	lsr.w	r11, r7, #6
	eor.w	r10, r10, r11
	tst.w	r10, #1
	bne	white
	mov	r3, r8
	b	store
white:
	mov	r3, r9
store:
	str	r3, [r4], #4
	subs	r5, r5, #1
	beq	done
	adds	r1, r1, #1
	subs	r2, r2, #1
	bne	pixel
	adds	r7, r7, #1
	b	row
done:
	dsb	sy
stop:
	wfe
	b	stop
.ltorg
.size _start, . - _start
#endif

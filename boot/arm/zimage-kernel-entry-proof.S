/* Thumb trampoline used immediately before __enter_kernel. */

.syntax unified
.arch armv7-a
.thumb

#ifdef TRAMPOLINE_ONLY
#ifndef BRANCH_INSTRUCTION
#error BRANCH_INSTRUCTION is required
#endif

.equ IMAGE_ENTRY, 0x80008000
.equ LINUX_ENTER, 0x82000a01

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function
.thumb_func
_start:
	ldr	r0, =IMAGE_ENTRY
	ldr	r1, =BRANCH_INSTRUCTION
	str	r1, [r0]
	dsb	sy
	ldr.w	pc, [pc, #0]
	.word	LINUX_ENTER
	.ltorg
.size _start, . - _start
#endif

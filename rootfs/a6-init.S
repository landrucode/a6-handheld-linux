/* Minimal ARM EABI PID 1 for the first A6 userspace handoff. */
.syntax unified
.arch armv7-a
.arm

.section .text, "ax", %progbits
.global _start
.type _start, %function
_start:
	mov	r0, #1
	adr	r1, message
	mov	r2, #27
	mov	r7, #4
	svc	#0
1:	wfe
	b	1b
message:
	.ascii "A6 Linux entered userspace\n"
message_end:
.size _start, . - _start

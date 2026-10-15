/*
 * A6 kernelcache handoff marker.
 *
 * This is copied into an executable zero-filled gap inside the known-good
 * kernelcache. The Mach-O entry point is patched to branch here. It paints a
 * small marker and then waits forever, so the test never enters XNU or writes
 * phone storage.
 */

.syntax unified
.arch armv7-a
.arm

.equ FRAMEBUFFER, 0xbf7aa000
.equ SCREEN_STRIDE, 4544
.equ MARKER_SIZE, 64
.equ MARKER_COLOR, 0x00ff0000

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function

_start:
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

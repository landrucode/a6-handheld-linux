/* A6 iBEC/XNU-entry to ARM Linux zImage handoff. */

.syntax unified
.arch armv7-a
.arm

#ifndef PAYLOAD_SIZE
#error PAYLOAD_SIZE must be supplied by the build script
#endif

#ifndef PAYLOAD_SOURCE_ADDRESS
#define PAYLOAD_SOURCE_ADDRESS 0x80100000
#endif
.equ PAYLOAD_SOURCE,      PAYLOAD_SOURCE_ADDRESS
.equ PAYLOAD_DESTINATION, 0x82000000
.equ CACHE_LINE_SIZE,     64

.section .text.boot, "ax", %progbits
.global _start
.type _start, %function

_start:
	cpsid   if
	mov     r11, r0                 /* Apple boot_args pointer */
#ifdef A6_MEMORY_CAPTURE
    /* Use only the already-reserved scratch page; preserve firmware SP.
     * C output ends at83fffc00, bounded nonrecursive stack above it.
     */
    mov r10, sp
    ldr sp, =0x83fffff0
    bl a6_capture_memory
    mov sp, r10
    ldr r0, =0x83fff100
    ldr r1, =0x83fffc00
90: mcr p15, 0, r0, c7, c14, 1
    add r0, r0, #64
    cmp r0, r1
    blo 90b
    dsb sy
#endif
	/* Preserve live video details where the decompressor can find them. */
	ldr     r5, [r11, #0x14]
	ldr     r6, [r11, #0x1c]
	ldr     r7, [r11, #0x24]
	mov     r9, r6
	mul     r6, r7, r6
	lsr     r6, r6, #2
	ldr     r8, =0x83fff000
	str     r5, [r8]
	str     r6, [r8, #4]
	str     r9, [r8, #8]
	mcr     p15, 0, r8, c7, c14, 1
	dsb     sy
	ldr     r4, =0x00ff0000        /* stage 1: shim entered */
	bl      paint_screen

	/* Move the complete zImage+DTB away from its expansion destination. */
	ldr     r0, =PAYLOAD_SOURCE
	ldr     r1, =PAYLOAD_DESTINATION
	ldr     r2, =PAYLOAD_SIZE
1:
	ldr     r3, [r0], #4
	str     r3, [r1], #4
	subs    r2, r2, #4
	bne     1b

	ldr     r4, =0x0000ff00        /* stage 2: relocation complete */
	bl      paint_screen

	/* Make the copied image visible before disabling the data cache. */
	ldr     r0, =PAYLOAD_DESTINATION
	ldr     r1, =(PAYLOAD_DESTINATION + PAYLOAD_SIZE)
2:
	mcr     p15, 0, r0, c7, c14, 1
	add     r0, r0, #CACHE_LINE_SIZE
	cmp     r0, r1
	blo     2b
	dsb     sy

	/* Linux requires MMU and data cache off at zImage entry. */
	mrc     p15, 0, r3, c1, c0, 0
	bic     r3, r3, #1
	bic     r3, r3, #4
	mcr     p15, 0, r3, c1, c0, 0
	dsb     sy
	isb     sy

	/* DT-only Linux boot protocol. The appended DTB replaces r2. */
	mov     r0, #0
	mvn     r1, #0
	mov     r2, #0
	ldr     r3, =PAYLOAD_DESTINATION
	bx      r3

/* Paint only after validating the dimensions supplied by iBEC. */
paint_screen:
	ldr     r0, [r11, #0x14]       /* Boot_Video.v_baseAddr */
	ldr     r1, [r11, #0x1c]       /* Boot_Video.v_rowBytes */
	ldr     r2, [r11, #0x24]       /* Boot_Video.v_height */
	cmp     r0, #0
	bxeq    lr
	cmp     r1, #0
	bxeq    lr
	cmp     r1, #8192
	bxhi    lr
	cmp     r2, #0
	bxeq    lr
	cmp     r2, #4096
	bxhi    lr
	mul     r2, r1, r2
	lsr     r2, r2, #2
3:
	str     r4, [r0], #4
	subs    r2, r2, #1
	bne     3b
	bx      lr

.ltorg
.size _start, . - _start

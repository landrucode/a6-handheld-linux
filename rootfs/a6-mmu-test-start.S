.syntax unified
.arch armv7-a
.arm
.text
.global _start
.type _start,%function
_start:
    bl main
    mov r7, #1
    svc #0
1:  b 1b
.section .note.GNU-stack,"",%progbits

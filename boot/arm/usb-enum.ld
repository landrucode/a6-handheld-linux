ENTRY(usb_enum_main)
SECTIONS {
    . = 0x80cbc900;
    .text : { KEEP(*(.text.entry)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss (NOLOAD) : { *(.bss*) *(COMMON) }
    __payload_end = .;
    ASSERT(__payload_end < 0x80cc9900, "USB payload overlaps reserved 8KiB stack")
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }
}

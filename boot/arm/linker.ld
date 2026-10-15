/* The recovery iBEC file-transfer path places the uploaded buffer at 0x80000000. */
ENTRY(_start)

SECTIONS
{
	. = 0x80000000;

	.text : ALIGN(4)
	{
		KEEP(*(.text.boot))
		*(.text*)
		*(.rodata*)
	}

	/DISCARD/ :
	{
		*(.comment)
		*(.note*)
		*(.ARM.attributes)
	}
}

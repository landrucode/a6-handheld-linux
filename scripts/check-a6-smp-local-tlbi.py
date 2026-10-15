#!/usr/bin/env python3
"""Check generated instructions and call relocations in the isolated candidate."""
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
output = Path(sys.argv[2])
output.mkdir(parents=True, exist_ok=True)
config = (root / ".config").read_text()
if "CONFIG_SMP=y\n" not in config or "CONFIG_ARM_ERRATA_720789=y\n" in config:
    raise SystemExit("requires the isolated Swift SMP configuration without 720789")
if "CONFIG_GENERIC_IRQ_IPI_MUX=y\n" not in config:
    raise SystemExit("A6 SMP IPI mux is absent")
for relative in ("arch/arm/kernel/smp_tlb.o", "arch/arm/mm/tlb-v7.o",
                 "arch/arm/mm/context.o"):
    obj = root / relative
    disassembly = subprocess.check_output(["llvm-objdump", "-dr", str(obj)], text=True)
    (output / (obj.stem + ".txt")).write_text(disassembly)
    lines = disassembly.splitlines()
    instructions = [line for line in lines if "mcr" in line or "mrc" in line]
    if any("mcr" in line and "c8, c3," in line for line in instructions):
        raise SystemExit(f"shareable TLBI remains in {relative}")
    if obj.stem == "smp_tlb":
        if "on_each_cpu_cond_mask" not in disassembly:
            raise SystemExit("missing software broadcast call relocation")
        if any("mrc" in line and "c0, c1, #0x7" in line for line in instructions):
            raise SystemExit("MMFR3 hardware-broadcast selection remains")
        for operation in ("#0x0", "#0x1", "#0x2"):
            if not any("mcr" in line and "c8, c7," in line and operation in line
                       for line in instructions):
                raise SystemExit(f"missing local TLBI {operation}")
    elif obj.stem == "tlb-v7":
        if sum("mcr" in line and "c8, c7, #0x1" in line for line in instructions) != 2:
            raise SystemExit("expected two local range loops")
    elif not any("mcr" in line and "c8, c7, #0x0" in line for line in instructions):
        raise SystemExit("missing local rollover flush")
aic = root / "drivers/irqchip/irq-apple-a6-aic.o"
aic_disassembly = subprocess.check_output(["llvm-objdump", "-dr", str(aic)], text=True)
(output / "irq-apple-a6-aic.txt").write_text(aic_disassembly)
for symbol in ("a6_aic_starting_cpu", "a6_aic_send_ipi", "ipi_mux_process",
               "ipi_mux_create", "set_smp_ipi_range", "__cpuhp_setup_state"):
    if symbol not in aic_disassembly:
        raise SystemExit(f"A6 AIC SMP path missing {symbol}")
print("PASS: software broadcast, local full/page/ASID/range/rollover and compiled AIC IPI mux")

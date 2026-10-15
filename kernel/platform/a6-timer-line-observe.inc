
/* Causal line test: change only CNTV IMASK, never the deadline or AIC mapping. */
#include <linux/irqflags.h>
extern void a6_diag_timer_row(unsigned int row, const char *text);
void a6_line_observe(void);

static void line_row(unsigned int row, const char *name, u32 value)
{
    char text[26];
    unsigned int i;
    for (i = 0; i < 25; i++) text[i] = ' ';
    text[25] = 0;
    for (i = 0; i < 16 && name[i]; i++) text[i] = name[i];
    for (i = 0; i < 8; i++)
        text[17+i] = "0123456789ABCDEF"[(value >> (28-4*i)) & 15];
    a6_diag_timer_row(row, text);
}

void a6_line_observe(void)
{
    u32 hw[4][6], ctl[4], elapsed[4], saved, cpsr, mask, target;
    u32 phase, bank, start, spins, value, changed[6], other = 0;
    u32 valid = 1, result, restored;
    unsigned long flags;

    line_row(0, "TIMER LINE START", 0);
    if (!a6_aic_base) { line_row(0, "AIC NOT MAPPED", 3); return; }
    asm volatile("mrs %0, cpsr" : "=r" (cpsr));
    asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (saved));
    mask = readl(a6_aic_base + AIC_MASK_SET + 20);
    target = readl(a6_aic_base + AIC_TARGET_CPU + 0xa2 * 4);
    /* Only probe an already enabled, expired, unmasked timer. Source a2
     * stays controller-masked. No IRQ dispatch can change CNTV mid-sample. */
    if ((saved & 7) != 5 || !(mask & BIT(2))) {
        line_row(0, "TIMER LINE SKIP", 3);
        line_row(1, "CTL ORIGINAL", saved);
        line_row(2, "AIC MASK BANK 5", mask);
        return;
    }
    local_irq_save(flags);
    for (phase = 0; phase < 4; phase++) {
        /* mask, unmask, mask, unmask: repeatability, not coincidence. */
        value = (phase & 1) ? saved : saved | BIT(1);
        asm volatile("mcr p15, 0, %0, c14, c3, 1\n\tisb" : : "r" (value));
        start = a6_trace_aic_clock();
        for (spins = 0; spins < 1000000; spins++) {
            if ((u32)(a6_trace_aic_clock() - start) >= 24000) break;
            cpu_relax();
        }
        elapsed[phase] = a6_trace_aic_clock() - start;
        if (elapsed[phase] < 24000) valid = 0;
        asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (ctl[phase]));
        if ((ctl[phase] & 7) != ((phase & 1) ? 5 : 7)) valid = 0;
        for (bank = 0; bank < 6; bank++)
            hw[phase][bank] = readl(a6_aic_base + 0x4200 + bank * 4);
    }
    asm volatile("mcr p15, 0, %0, c14, c3, 1\n\tisb" : : "r" (saved));
    asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (restored));
    local_irq_restore(flags);
    for (bank = 0; bank < 6; bank++) {
        /* Only lines LOW in both masked samples and HIGH in both unmasked. */
        changed[bank] = ~hw[0][bank] & hw[1][bank] & ~hw[2][bank] & hw[3][bank];
        if (bank != 5) other |= changed[bank];
    }
    result = !valid ? 3 : (changed[5] == BIT(2) && !other ? 1 : 2);
    line_row(0, "TIMER LINE RESULT", result);
    line_row(1, "CTL ORIGINAL", saved);
    line_row(2, "MASK 1 CTL", ctl[0]);
    line_row(3, "MASK 1 BANK 5", hw[0][5]);
    line_row(4, "UNMASK 1 CTL", ctl[1]);
    line_row(5, "UNMASK 1 BANK 5", hw[1][5]);
    line_row(6, "MASK 2 CTL", ctl[2]);
    line_row(7, "MASK 2 BANK 5", hw[2][5]);
    line_row(8, "UNMASK 2 CTL", ctl[3]);
    line_row(9, "UNMASK 2 BANK 5", hw[3][5]);
    line_row(10, "CTL RESTORED", restored);
    line_row(11, "AIC MASK BANK 5", mask);
    line_row(12, "A2 TARGET", target);
    line_row(13, "CPSR BEFORE", cpsr);
    for (bank = 0; bank < 6; bank++) {
        char label[] = "FOLLOW BANK 0";
        label[12] += bank;
        line_row(14+bank, label, changed[bank]);
    }
    for (phase = 0; phase < 4; phase++) {
        char label[] = "ELAPSED PHASE 0";
        label[14] += phase;
        line_row(20+phase, label, elapsed[phase]);
    }
}


/* One controlled software IRQ on the existing timer source; diagnostic only. */
#include <linux/irqflags.h>
extern void a6_diag_timer_row(unsigned int row, const char *text);
void a6_route_observe(void);

static void route_row(unsigned int row, const char *name, u32 value)
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

void a6_route_observe(void)
{
    const u32 bank = 20, bit = BIT(3); /* hwirq 0xa3 only */
    u32 mask0, sw0, target, who, config, hw[6], cpsr, mpidr, ctl, ctl1;
    u32 entry0, event0, entries, events, delivered, last, start, elapsed = 0;
    u32 spins, result = 3, i, masked_ctl;
    unsigned long flags;

    route_row(0, "AIC ROUTE START", 0);
    if (!a6_aic_base) { route_row(0, "AIC NOT MAPPED", 3); return; }
    asm volatile("mrs %0, cpsr" : "=r" (cpsr));
    asm volatile("mrc p15, 0, %0, c0, c0, 5" : "=r" (mpidr));
    asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (ctl));
    who = readl(a6_aic_base + 0x2000);
    config = readl(a6_aic_base + 0x10);
    target = readl(a6_aic_base + AIC_TARGET_CPU + 0xa3 * 4);
    mask0 = readl(a6_aic_base + AIC_MASK_SET + bank);
    sw0 = readl(a6_aic_base + AIC_SW_SET + bank);
    for (i = 0; i < 6; i++) hw[i] = readl(a6_aic_base + 0x4200 + i * 4);
    entry0 = READ_ONCE(route_entries);
    event0 = READ_ONCE(a6_trace_aic_count);

    /* Refuse to steal an existing software latch or change CPU IRQ state.
     * Keep the source's existing target/mask. Mask only the real timer while
     * probing so a synthetic delivery cannot be confused with its deadline. */
    if (!(sw0 & bit) && !(cpsr & BIT(7))) {
        masked_ctl = ctl | BIT(1);
        asm volatile("mcr p15, 0, %0, c14, c3, 1\n\tisb" : : "r" (masked_ctl));
        WRITE_ONCE(route_active, true);
        start = a6_trace_aic_clock();
        writel(bit, a6_aic_base + AIC_SW_SET + bank);
        for (spins = 0; spins < 10000000; spins++) {
            if (READ_ONCE(route_delivered)) break;
            if ((u32)(a6_trace_aic_clock() - start) >= 4800000) break;
            cpu_relax();
        }
        elapsed = a6_trace_aic_clock() - start;
        result = READ_ONCE(route_delivered) ? 1 : 2;
        local_irq_save(flags);
        entries = route_entries - entry0;
        events = a6_trace_aic_count - event0;
        delivered = route_delivered;
        last = a6_trace_aic_last;
        writel(bit, a6_aic_base + AIC_SW_CLR + bank);
        WRITE_ONCE(route_active, false);
        writel(bit, a6_aic_base + ((mask0 & bit) ? AIC_MASK_SET : AIC_MASK_CLR) + bank);
        asm volatile("mcr p15, 0, %0, c14, c3, 1\n\tisb" : : "r" (ctl));
        local_irq_restore(flags);
    } else {
        entries = events = delivered = 0;
        last = READ_ONCE(a6_trace_aic_last);
    }
    asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (ctl1));
    route_row(0, "AIC ROUTE RESULT", result);
    route_row(1, "SOURCE HWIRQ", 0xa3);
    route_row(2, "AIC WHOAMI", who);
    route_row(3, "TARGET BEFORE", target);
    route_row(4, "MASK BEFORE", mask0);
    route_row(5, "MASK RESTORED", readl(a6_aic_base + AIC_MASK_SET + bank));
    route_row(6, "SW BEFORE", sw0);
    route_row(7, "SW RESTORED", readl(a6_aic_base + AIC_SW_SET + bank));
    route_row(8, "CPU IRQ ENTRIES", entries);
    route_row(9, "AIC EVENT DELTA", events);
    route_row(10, "SYNTHETIC SEEN", delivered);
    route_row(11, "LAST EVENT", last);
    route_row(12, "CPSR BEFORE", cpsr);
    route_row(13, "TIMER CTL BEFORE", ctl);
    route_row(14, "TIMER CTL AFTER", ctl1);
    route_row(15, "AIC ELAPSED", elapsed);
    for (i = 0; i < 6; i++) {
        char label[] = "HW LINES BANK 0";
        label[14] += i;
        route_row(16+i, label, hw[i]);
    }
    route_row(22, "CPU MPIDR", mpidr);
    route_row(23, "AIC CONFIG", config);
}

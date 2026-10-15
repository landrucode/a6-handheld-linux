
/* Diagnostic only: bounded awake observation, then original PHY msleep. */
#include <linux/jiffies.h>
extern u32 a6_trace_aic_count, a6_trace_aic_last, a6_trace_aic_info;
extern u32 a6_trace_aic_clock(void);
extern void a6_diag_timer_row(unsigned int row, const char *text);
void a6_timer_observe(void);

static void trace_row(unsigned int row, const char *name, u32 value)
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

void a6_timer_observe(void)
{
    u32 start, elapsed, spins, cpsr, ctl0, tv0, tv1;
    u32 j0, jd, irq0, irqd, ai0, aid, ctl1, cd;
    u64 c0;

    trace_row(0, "TIMER OBSERVE", 0);
    asm volatile("mrs %0, cpsr" : "=r" (cpsr));
    ctl0 = a6_cntv_ctl_read();
    asm volatile("mrc p15, 0, %0, c14, c3, 0" : "=r" (tv0));
    j0 = READ_ONCE(jiffies);
    irq0 = READ_ONCE(trace_irqs);
    ai0 = READ_ONCE(a6_trace_aic_count);
    c0 = a6_counter_read();
    start = a6_trace_aic_clock();
    /* Independent 24 MHz AIC clock; hard cap also handles a dead clock.
     * No IRQ enabling, EVENT reads, register writes, or scheduler calls. */
    for (spins = 0; spins < 10000000; spins++) {
        if ((u32)(a6_trace_aic_clock() - start) >= 4800000) break;
        cpu_relax();
    }
    elapsed = a6_trace_aic_clock() - start;
    cd = a6_counter_read() - c0;
    jd = READ_ONCE(jiffies) - j0;
    irqd = READ_ONCE(trace_irqs) - irq0;
    aid = READ_ONCE(a6_trace_aic_count) - ai0;
    ctl1 = a6_cntv_ctl_read();
    asm volatile("mrc p15, 0, %0, c14, c3, 0" : "=r" (tv1));
    trace_row(0, "TIMER REPORT HEX", 1);
    trace_row(1, "INIT STAGE", trace_stage);
    trace_row(2, "INIT ERROR", trace_error);
    trace_row(3, "CNTFRQ", trace_freq);
    trace_row(4, "RATE HZ", a6_counter_rate);
    trace_row(5, "LINUX IRQ", a6_clockevent.irq);
    trace_row(6, "PROGRAM COUNT", trace_programs);
    trace_row(7, "LAST DEADLINE", trace_delta);
    trace_row(8, "TIMER IRQ TOTAL", READ_ONCE(trace_irqs));
    trace_row(9, "TIMER IRQ DELTA", irqd);
    trace_row(10, "JIFFIES DELTA", jd);
    trace_row(11, "CTL BEFORE", ctl0);
    trace_row(12, "CTL AFTER", ctl1);
    trace_row(13, "TVAL BEFORE", tv0);
    trace_row(14, "TVAL AFTER", tv1);
    trace_row(15, "AIC IRQ COUNT", a6_trace_aic_info);
    trace_row(16, "AIC EVENT DELTA", aid);
    trace_row(17, "AIC LAST EVENT", READ_ONCE(a6_trace_aic_last));
    trace_row(18, "CPSR BEFORE", cpsr);
    trace_row(19, "AIC ELAPSED", elapsed);
    trace_row(20, "COUNTER DELTA", cd);
    trace_row(21, "LOOP ITERATIONS", spins);
    trace_row(22, "EVENT HANDLER", (u32)a6_clockevent.event_handler);
    trace_row(23, "EVENT STATE", a6_clockevent.state_use_accessors);
}

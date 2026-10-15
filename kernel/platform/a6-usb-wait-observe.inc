/* Five-second, bounded, IRQ-state-preserving window before userspace exec. */
#include <linux/jiffies.h>
extern u32 a6_trace_aic_clock(void);
void a6_usb_report_sync(void)
{
    u32 cpsr, start, elapsed, j0, jd, irq0, irqd, setup0, setupd, spins;

    usb_report_row(0, "USB WAIT START", 0);
    asm volatile("mrs %0, cpsr" : "=r" (cpsr));
    if (cpsr & BIT(7)) {
        usb_report_row(0, "WAIT IRQ MASKED", cpsr);
        return;
    }
    j0 = READ_ONCE(jiffies);
    irq0 = READ_ONCE(a6_usb_diag[6]);
    setup0 = READ_ONCE(a6_usb_diag[8]);
    start = a6_trace_aic_clock();
    /* No sleep/workqueue dependency, IRQ forcing, register changes or polling
     * USB servicing. USB requests must be handled by the existing IRQ path.
     * This UP voluntary-preemption busy interval does not promise worker time. */
    for (spins = 0; spins < 50000000; spins++) {
        if ((u32)(a6_trace_aic_clock() - start) >= 120000000) break;
        cpu_relax();
    }
    elapsed = a6_trace_aic_clock() - start;
    jd = READ_ONCE(jiffies) - j0;
    irqd = READ_ONCE(a6_usb_diag[6]) - irq0;
    setupd = READ_ONCE(a6_usb_diag[8]) - setup0;
    a6_usb_report_work(NULL);
    usb_report_row(0, "WAIT AIC TICKS", elapsed);
    usb_report_row(1, "WAIT LINUX TICKS", jd);
    usb_report_row(3, "WAIT USB IRQS", irqd);
    usb_report_row(4, "WAIT SETUPS", setupd);
    /* Remaining rows retain probe return, bind return and full USB snapshot.
     * Return to the original run_init_process; never claim userspace success. */
}

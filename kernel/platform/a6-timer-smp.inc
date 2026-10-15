// SPDX-License-Identifier: GPL-2.0-only
/* Opt-in CPU1 local event, appended only to the Linux bridge profile.
 * IRQ ownership follows the pinned timer-tegra/exynos_mct CPU-start path:
 * request while masked, force affinity, register on its receiving CPU.
 */
#include <linux/cpuhotplug.h>
#include <linux/sysfs.h>

extern void a6_smp_aic_timer_snapshot(u32 *hw, u32 *mask, u32 *target);
static u32 a6_line_hw[4][6], a6_line_mask[4][6], a6_line_target[4][3];
static u32 a6_line_ctl[4], a6_line_elapsed[4], a6_line_follow[6];
static u32 a6_line_result, a6_line_hwirq = U32_MAX, a6_line_before, a6_line_after;

/* CPU1 owns CNTV, before any Linux clockevent or RCU enlistment. IRQ/FIQ off.
 * Program one expired deadline; modulate only IMASK during the four phases.
 * AIC EVENT is never read. Finish disabled/masked before the usual setup.
 */
int a6_smp_timer_line_probe(void);
int a6_smp_timer_line_probe(void)
{
    unsigned int phase, bank, spins, count = 0;
    u64 start;
    bool valid = true;

    a6_line_before = a6_cntv_ctl_read();
    a6_cntv_ctl_write(CNTV_CTL_IMASK);
    a6_cntv_tval_write(1);
    for (phase = 0; phase < 4; phase++) {
        a6_cntv_ctl_write(CNTV_CTL_ENABLE | ((phase & 1) ? 0 : CNTV_CTL_IMASK));
        start = a6_counter_read();
        for (spins = 0; spins < 1000000; spins++) {
            if (a6_counter_read() - start >= 24000)
                break;
            cpu_relax();
        }
        a6_line_elapsed[phase] = a6_counter_read() - start;
        a6_line_ctl[phase] = a6_cntv_ctl_read();
        if (a6_line_elapsed[phase] < 24000 ||
            (a6_line_ctl[phase] & 3) != ((phase & 1) ? 1 : 3) ||
            ((phase & 1) && !(a6_line_ctl[phase] & 4)))
            valid = false;
        a6_smp_aic_timer_snapshot(a6_line_hw[phase], a6_line_mask[phase],
                                   a6_line_target[phase]);
    }
    a6_cntv_ctl_write(CNTV_CTL_IMASK);
    a6_line_after = a6_cntv_ctl_read();
    for (bank = 0; bank < 6; bank++) {
        u32 follow = ~a6_line_hw[0][bank] & a6_line_hw[1][bank] &
                     ~a6_line_hw[2][bank] & a6_line_hw[3][bank];
        a6_line_follow[bank] = follow;
        count += hweight32(follow);
        if (follow)
            a6_line_hwirq = bank * 32 + __ffs(follow);
    }
    a6_line_result = !valid ? 3 : count == 1 ? 1 : 2;
    pr_info("A6 CPU1 timer line: result=%u hwirq=%u ctl=%x/%x/%x/%x end=%x\n",
            a6_line_result, a6_line_hwirq, a6_line_ctl[0], a6_line_ctl[1],
            a6_line_ctl[2], a6_line_ctl[3], a6_line_after);
    return valid ? 0 : -EPROTO;
}

static struct clock_event_device a6_cpu1_clockevent;
static bool a6_cpu1_timer_prepared, a6_cpu1_timer_ready;
static u32 a6_cpu1_timer_irqs;
static u32 a6_cpu1_timer_cntfrq;
static int a6_cpu1_timer_start_result = -EAGAIN;

bool a6_smp_timer_prepared(void);
bool a6_smp_timer_prepared(void)
{
	return READ_ONCE(a6_cpu1_timer_prepared);
}

ssize_t a6_smp_timer_status(char *buf);
ssize_t a6_smp_timer_status(char *buf)
{
	ssize_t used;
	unsigned int phase, bank;
	used = sysfs_emit(buf,
		"A6_SMP_TIMER_V1 kind=local registration=early_time_init checkpoint=explicit_before_rcu prepared=%u ready=%u start_result=%d irq=%d cntfrq=%u irqs=%u\n",
		a6_cpu1_timer_prepared, a6_cpu1_timer_ready,
		a6_cpu1_timer_start_result, a6_cpu1_clockevent.irq,
		a6_cpu1_timer_cntfrq, READ_ONCE(a6_cpu1_timer_irqs));
    used += sysfs_emit_at(buf, used, "A6_CPU1_TIMER_LINE result=%u hwirq=%u before=%08x after=%08x\n",
                         a6_line_result, a6_line_hwirq, a6_line_before, a6_line_after);
    for (phase = 0; phase < 4; phase++) {
        used += sysfs_emit_at(buf, used, "phase%u ctl=%08x elapsed=%u target_a2_a5_a6=%08x/%08x/%08x hw=", phase,
                a6_line_ctl[phase], a6_line_elapsed[phase], a6_line_target[phase][0],
                a6_line_target[phase][1], a6_line_target[phase][2]);
        for (bank = 0; bank < 6; bank++)
            used += sysfs_emit_at(buf, used, "%08x%s", a6_line_hw[phase][bank], bank == 5 ? " mask=" : "/");
        for (bank = 0; bank < 6; bank++)
            used += sysfs_emit_at(buf, used, "%08x%s", a6_line_mask[phase][bank], bank == 5 ? "\n" : "/");
    }
    used += sysfs_emit_at(buf, used, "follow=%08x/%08x/%08x/%08x/%08x/%08x\n",
            a6_line_follow[0], a6_line_follow[1], a6_line_follow[2],
            a6_line_follow[3], a6_line_follow[4], a6_line_follow[5]);
    return used;
}

bool a6_smp_timer_ready(unsigned int cpu);
bool a6_smp_timer_ready(unsigned int cpu)
{
	return cpu == 0 || (cpu == 1 && READ_ONCE(a6_cpu1_timer_ready));
}

void a6_smp_timer_quiesce(void);
void a6_smp_timer_quiesce(void)
{
	a6_cntv_ctl_write(CNTV_CTL_IMASK);
	isb();
}

static int a6_cpu1_next_event(unsigned long delta,
			    struct clock_event_device *evt)
{
	/* CPU1 does not modify CPU0's diagnostic program/IRQ counters. */
	a6_cntv_tval_write(delta);
	a6_cntv_ctl_write(CNTV_CTL_ENABLE);
	return 0;
}

static irqreturn_t a6_cpu1_timer_interrupt(int irq, void *data)
{
	struct clock_event_device *evt = data;
	a6_cntv_ctl_write(a6_cntv_ctl_read() | CNTV_CTL_IMASK);
	a6_cpu1_timer_irqs++;
	evt->event_handler(evt);
	return IRQ_HANDLED;
}

static int a6_cpu1_timer_starting(unsigned int cpu)
{
	u32 cntfrq;
	int ret;

	if (cpu == 0)
		return 0;
	if (cpu != 1 || !a6_cpu1_timer_prepared)
		return -ENODEV;
	a6_timer_shutdown(&a6_cpu1_clockevent);
	asm volatile("mrc p15, 0, %0, c14, c0, 0" : "=r" (cntfrq));
	a6_cpu1_timer_cntfrq = cntfrq;
	if (cntfrq != a6_counter_rate) {
		a6_cpu1_timer_start_result = -EPROTO;
		return -EPROTO;
	}
	ret = irq_force_affinity(a6_cpu1_clockevent.irq, cpumask_of(cpu));
	if (ret) {
		a6_cpu1_timer_start_result = ret;
		return ret;
	}
	/* The local timer remains masked until Linux programs its event. */
	enable_irq(a6_cpu1_clockevent.irq);
	clockevents_config_and_register(&a6_cpu1_clockevent, a6_counter_rate,
					0xf, U32_MAX);
	WRITE_ONCE(a6_cpu1_timer_ready, true);
	a6_cpu1_timer_start_result = 0;
	pr_info("A6 timer: CPU1 local event ready, IRQ %d, rate %u\n",
		a6_cpu1_clockevent.irq, cntfrq);
	return 0;
}

int a6_smp_timer_checkpoint_start(unsigned int cpu);
int a6_smp_timer_checkpoint_start(unsigned int cpu)
{
	return a6_cpu1_timer_starting(cpu);
}

static int __init a6_cpu1_timer_init(struct device_node *node)
{
	int irq, ret;

	irq = irq_of_parse_and_map(node, 1);
	if (!irq)
		return -EINVAL;
	a6_cpu1_clockevent.name = "apple-a6-timer-cpu1";
	a6_cpu1_clockevent.rating = 400;
	a6_cpu1_clockevent.features = CLOCK_EVT_FEAT_ONESHOT;
	a6_cpu1_clockevent.set_state_shutdown = a6_timer_shutdown;
	a6_cpu1_clockevent.set_state_oneshot = a6_timer_oneshot;
	a6_cpu1_clockevent.tick_resume = a6_timer_shutdown;
	a6_cpu1_clockevent.set_next_event = a6_cpu1_next_event;
	a6_cpu1_clockevent.cpumask = cpumask_of(1);
	a6_cpu1_clockevent.irq = irq;
	ret = request_irq(irq, a6_cpu1_timer_interrupt,
			  IRQF_TIMER | IRQF_NOBALANCING | IRQF_NO_AUTOEN,
			  "apple-a6-timer-cpu1", &a6_cpu1_clockevent);
	if (ret)
		return ret;
	a6_cpu1_timer_prepared = true;
	ret = cpuhp_setup_state(CPUHP_AP_APPLE_A6_TIMER_STARTING,
			       "timer/a6:starting", a6_cpu1_timer_starting, NULL);
	if (ret) {
		a6_cpu1_timer_prepared = false;
		free_irq(irq, &a6_cpu1_clockevent);
	}
	return ret;
}

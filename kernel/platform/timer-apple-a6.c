// SPDX-License-Identifier: GPL-2.0-only
/* Apple A6 generic-counter timer wiring, as used by iOS 8.4.1 XNU. */

#include <linux/clockchips.h>
#include <linux/clocksource.h>
#include <linux/interrupt.h>
#include <linux/of.h>
#include <linux/of_irq.h>
#include <linux/sched_clock.h>

#define CNTV_CTL_ENABLE BIT(0)
#define CNTV_CTL_IMASK  BIT(1)

static struct clock_event_device a6_clockevent;
static u32 a6_counter_rate;

static u64 notrace a6_counter_read(void)
{
	u64 value;

	asm volatile("isb\n\tmrrc p15, 0, %Q0, %R0, c14" : "=r" (value));
	return value;
}

static u64 a6_clocksource_read(struct clocksource *cs)
{
	return a6_counter_read();
}

static struct clocksource a6_clocksource = {
	.name = "apple-a6-counter",
	.rating = 400,
	.read = a6_clocksource_read,
	.mask = CLOCKSOURCE_MASK(64),
	.flags = CLOCK_SOURCE_IS_CONTINUOUS,
};

/* The diagnostic build overrides these weak hooks with framebuffer markers. */
void a6_counter_proof(void);
void a6_timer_irq_proof(void);
void __weak a6_counter_proof(void) { }
void __weak a6_timer_irq_proof(void) { }

static u32 a6_cntv_ctl_read(void)
{
	u32 value;

	asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (value));
	return value;
}

static void a6_cntv_ctl_write(u32 value)
{
	asm volatile("mcr p15, 0, %0, c14, c3, 1\n\tisb" : : "r" (value));
}

static void a6_cntv_tval_write(u32 value)
{
	/* This is the exact deadline operation used by the matching XNU. */
	asm volatile("mcr p15, 0, %0, c14, c3, 0\n\tisb" : : "r" (value));
}

static int a6_timer_shutdown(struct clock_event_device *evt)
{
	a6_cntv_ctl_write(CNTV_CTL_IMASK);
	return 0;
}

static int a6_timer_oneshot(struct clock_event_device *evt)
{
	a6_cntv_ctl_write(CNTV_CTL_ENABLE);
	return 0;
}

static int a6_timer_next_event(unsigned long delta,
			       struct clock_event_device *evt)
{
	a6_cntv_tval_write(delta);
	a6_cntv_ctl_write(CNTV_CTL_ENABLE);
	return 0;
}

static irqreturn_t a6_timer_interrupt(int irq, void *data)
{
	struct clock_event_device *evt = data;
	static unsigned int irq_count;

	a6_cntv_ctl_write(a6_cntv_ctl_read() | CNTV_CTL_IMASK);
	if (++irq_count == 8)
		a6_timer_irq_proof();
	evt->event_handler(evt);
	return IRQ_HANDLED;
}

static int __init a6_timer_init(struct device_node *node)
{
	u64 before;
	u32 cntfrq;
	u32 spins;
	int irq, ret;

	asm volatile("mrc p15, 0, %0, c14, c0, 0" : "=r" (cntfrq));
	if (of_property_read_u32(node, "clock-frequency", &a6_counter_rate))
		a6_counter_rate = cntfrq;
	if (!a6_counter_rate)
		return -EINVAL;
	before = a6_counter_read();
	spins = 1000000;
	while (a6_counter_read() == before && --spins)
		cpu_relax();
	if (!spins)
		return -ENODEV;
	a6_counter_proof();

	irq = irq_of_parse_and_map(node, 0);
	if (!irq)
		return -EINVAL;

	ret = clocksource_register_hz(&a6_clocksource, a6_counter_rate);
	if (ret)
		return ret;

	sched_clock_register(a6_counter_read, 64, a6_counter_rate);
	a6_clockevent.name = "apple-a6-timer";
	a6_clockevent.rating = 400;
	a6_clockevent.features = CLOCK_EVT_FEAT_ONESHOT;
	a6_clockevent.set_state_shutdown = a6_timer_shutdown;
	a6_clockevent.set_state_oneshot = a6_timer_oneshot;
	a6_clockevent.tick_resume = a6_timer_shutdown;
	a6_clockevent.set_next_event = a6_timer_next_event;
	a6_clockevent.cpumask = cpumask_of(0);
	a6_clockevent.irq = irq;

	/* Mask at the timer before request_irq() unmasks the AIC vector. */
	a6_timer_shutdown(&a6_clockevent);
	ret = request_irq(irq, a6_timer_interrupt, IRQF_TIMER | IRQF_IRQPOLL,
			  "apple-a6-timer", &a6_clockevent);
	if (ret) {
		clocksource_unregister(&a6_clocksource);
		return ret;
	}

	clockevents_config_and_register(&a6_clockevent, a6_counter_rate, 0xf,
					U32_MAX);

	pr_info("A6 timer: counter %u Hz, IRQ %d\n", a6_counter_rate, irq);
	return 0;
}

TIMER_OF_DECLARE(apple_a6_timer, "apple,s5l8950-timer", a6_timer_init);

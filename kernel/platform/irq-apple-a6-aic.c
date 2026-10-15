// SPDX-License-Identifier: GPL-2.0-only
/* Apple A6/S5L8950 AIC v1; SMP IPI path is compile-only until CPU1 boots Linux. */

#include <linux/bitops.h>
#include <linux/cpuhotplug.h>
#include <linux/io.h>
#include <linux/irq.h>
#include <linux/irqchip.h>
#include <linux/irqdomain.h>
#include <linux/of_address.h>
#ifdef A6_AIC_USB_FAIRNESS
#include <linux/kobject.h>
#include <linux/sched/clock.h>
#include <linux/sysfs.h>
#include <linux/workqueue.h>
#endif

#include <asm/exception.h>
#ifdef CONFIG_SMP
#include <asm/smp.h>
#endif

#define AIC_INFO              0x0004
#define AIC_EVENT             0x2004
#define AIC_IPI_SEND          0x2008
#define AIC_IPI_ACK           0x200c
#define AIC_IPI_MASK_SET      0x2024
#define AIC_IPI_MASK_CLR      0x2028
#define AIC_IPI_OTHER         1
#define AIC_IPI_SELF          BIT(31)
#define AIC_TARGET_CPU        0x3000
#define AIC_SW_SET            0x4000
#define AIC_SW_CLR            0x4080
#define AIC_MASK_SET          0x4100
#define AIC_MASK_CLR          0x4180

#define AIC_EVENT_TYPE(v)     (((v) >> 16) & 0xff)
#define AIC_EVENT_IRQ         1
#define AIC_EVENT_IPI         4
#define AIC_EVENT_NUM(v)      ((v) & 0xffff)
#define AIC_MAX_IRQS          0x400

static void __iomem *a6_aic_base;
static struct irq_domain *a6_aic_domain;

#ifdef A6_AIC_USB_FAIRNESS
/* A continuously asserted gadget IRQ must not monopolize the EVENT loop.
 * Temporarily mask only USB after a sustained burst, then let timer/task
 * work run before rearming. No controller reset or changes to battery IRQs.
 */
#define A6_USB_HWIRQ 11
#define A6_USB_BURST_MIN 256
#define A6_USB_BURST_NS 4000000ULL
static unsigned int a6_usb_deferred_irq;
static bool a6_usb_pending;
static u32 a6_usb_deferrals, a6_usb_rearms, a6_aic_last_irq;
static u64 a6_aic_entry_ns, a6_aic_exit_ns, a6_usb_max_burst_ns;

static void a6_usb_rearm(struct work_struct *work)
{
	WRITE_ONCE(a6_usb_rearms, a6_usb_rearms + 1);
	WRITE_ONCE(a6_usb_pending, false);
	enable_irq(a6_usb_deferred_irq);
}
static DECLARE_DELAYED_WORK(a6_usb_rearm_work, a6_usb_rearm);

static bool a6_usb_yield(unsigned int hwirq, unsigned int streak, u64 elapsed)
{
	unsigned int virq;

	if (hwirq != A6_USB_HWIRQ || streak < A6_USB_BURST_MIN ||
	    elapsed < A6_USB_BURST_NS || READ_ONCE(a6_usb_pending))
		return false;
	virq = irq_find_mapping(a6_aic_domain, hwirq);
	if (!virq)
		return false;
	a6_usb_deferred_irq = virq;
	WRITE_ONCE(a6_usb_pending, true);
	disable_irq_nosync(virq);
	WRITE_ONCE(a6_usb_deferrals, a6_usb_deferrals + 1);
	WRITE_ONCE(a6_usb_max_burst_ns,
		   max(a6_usb_max_burst_ns, elapsed));
	/* IRQ depth is balanced by one rearm, including if the driver masks it. */
	if (!queue_delayed_work(system_wq, &a6_usb_rearm_work, 1)) {
		WRITE_ONCE(a6_usb_pending, false);
		enable_irq(virq);
	}
	return true;
}

static ssize_t progress_show(struct kobject *kobj,
			     struct kobj_attribute *attr, char *buf)
{
	return sysfs_emit(buf,
		"A6_AIC_USB_FAIRNESS_V1 deferrals=%u rearms=%u last_irq=%u entry_ns=%llu exit_ns=%llu max_burst_ns=%llu\n",
		READ_ONCE(a6_usb_deferrals), READ_ONCE(a6_usb_rearms),
		READ_ONCE(a6_aic_last_irq), READ_ONCE(a6_aic_entry_ns),
		READ_ONCE(a6_aic_exit_ns), READ_ONCE(a6_usb_max_burst_ns));
}
static struct kobj_attribute a6_aic_progress = __ATTR_RO(progress);

static int __init a6_aic_progress_init(void)
{
	struct kobject *kobj;
	int ret;

	kobj = kobject_create_and_add("a6_aic", firmware_kobj);
	if (!kobj)
		return -ENOMEM;
	ret = sysfs_create_file(kobj, &a6_aic_progress.attr);
	if (ret)
		kobject_put(kobj);
	return ret;
}
late_initcall(a6_aic_progress_init);
#endif

#ifdef CONFIG_SMP
/* The physical OTHER IPI is shared by the virtual ARM IPI messages. */
static void a6_aic_send_ipi(unsigned int cpu)
{
	writel(BIT(cpu), a6_aic_base + AIC_IPI_SEND);
}

static int a6_aic_starting_cpu(unsigned int cpu)
{
	/* CPU-local AIC window. Never read another CPU's EVENT register. */
	writel(AIC_IPI_SELF, a6_aic_base + AIC_IPI_MASK_SET);
	writel(AIC_IPI_SELF | AIC_IPI_OTHER,
	       a6_aic_base + AIC_IPI_ACK);
	writel(AIC_IPI_OTHER, a6_aic_base + AIC_IPI_MASK_CLR);
	return 0;
}

static void a6_aic_handle_ipi(void)
{
	writel(AIC_IPI_OTHER, a6_aic_base + AIC_IPI_ACK);
	ipi_mux_process();
	writel(AIC_IPI_OTHER, a6_aic_base + AIC_IPI_MASK_CLR);
}
#endif

static void a6_aic_mask(struct irq_data *d)
{
	writel_relaxed(BIT(d->hwirq & 31), a6_aic_base + AIC_MASK_SET +
			 (d->hwirq >> 5) * 4);
}

static void a6_aic_unmask(struct irq_data *d)
{
	writel_relaxed(BIT(d->hwirq & 31), a6_aic_base + AIC_MASK_CLR +
			 (d->hwirq >> 5) * 4);
}

static void a6_aic_eoi(struct irq_data *d)
{
	/* EVENT reads acknowledge and mask. Re-enable unless Linux masked it. */
	if (!irqd_irq_masked(d))
		a6_aic_unmask(d);
}

static struct irq_chip a6_aic_chip = {
	.name = "A6-AIC",
	.irq_mask = a6_aic_mask,
	.irq_unmask = a6_aic_unmask,
	.irq_eoi = a6_aic_eoi,
};

static int a6_aic_map(struct irq_domain *d, unsigned int virq,
		      irq_hw_number_t hwirq)
{
	if (hwirq >= d->revmap_size)
		return -EINVAL;

	irq_set_chip_and_handler(virq, &a6_aic_chip, handle_fasteoi_irq);
	irq_set_probe(virq);
	return 0;
}

static const struct irq_domain_ops a6_aic_domain_ops = {
	.map = a6_aic_map,
	.xlate = irq_domain_xlate_onecell,
};

static void __exception_irq_entry a6_aic_handle_irq(struct pt_regs *regs)
{
	u32 event;
#ifdef A6_AIC_USB_FAIRNESS
	u32 streak = 0;
	u64 burst_start = sched_clock();

	WRITE_ONCE(a6_aic_entry_ns, burst_start);
#endif

	while ((event = readl(a6_aic_base + AIC_EVENT))) {
#ifdef A6_AIC_USB_FAIRNESS
		WRITE_ONCE(a6_aic_last_irq, event);
		if (AIC_EVENT_NUM(event) == A6_USB_HWIRQ &&
		    AIC_EVENT_TYPE(event) == AIC_EVENT_IRQ) {
			if (!streak)
				burst_start = sched_clock();
			streak++;
		} else {
			streak = 0;
		}
#endif
		if (AIC_EVENT_TYPE(event) == AIC_EVENT_IRQ)
			generic_handle_domain_irq(a6_aic_domain,
					  AIC_EVENT_NUM(event));
#ifdef CONFIG_SMP
		else if (AIC_EVENT_TYPE(event) == AIC_EVENT_IPI &&
			 AIC_EVENT_NUM(event) == AIC_IPI_OTHER)
			a6_aic_handle_ipi();
#endif
		else
			pr_warn_ratelimited("A6 AIC: unexpected event %#x\n", event);
#ifdef A6_AIC_USB_FAIRNESS
		if (streak && a6_usb_yield(AIC_EVENT_NUM(event), streak,
					 sched_clock() - burst_start))
			streak = 0;
#endif
	}
#ifdef A6_AIC_USB_FAIRNESS
	WRITE_ONCE(a6_aic_exit_ns, sched_clock());
#endif
}

static int __init a6_aic_init(struct device_node *node,
			      struct device_node *parent)
{
	u32 nr_irqs, i;
#ifdef CONFIG_SMP
	int base_ipi;
#endif

	a6_aic_base = of_iomap(node, 0);
	if (!a6_aic_base)
		return -ENOMEM;

	nr_irqs = readl_relaxed(a6_aic_base + AIC_INFO) & 0xffff;
	if (!nr_irqs || nr_irqs > AIC_MAX_IRQS)
		return -EINVAL;

	a6_aic_domain = irq_domain_create_linear(of_fwnode_handle(node), nr_irqs,
					     &a6_aic_domain_ops, NULL);
	if (!a6_aic_domain)
		return -ENOMEM;

	for (i = 0; i < DIV_ROUND_UP(nr_irqs, 32); i++) {
		writel_relaxed(~0U, a6_aic_base + AIC_MASK_SET + i * 4);
		writel_relaxed(~0U, a6_aic_base + AIC_SW_CLR + i * 4);
	}
	/* TARGET_CPU is a CPU bitmask; BIT(0) routes every wired IRQ to CPU0. */
	for (i = 0; i < nr_irqs; i++)
		writel_relaxed(1, a6_aic_base + AIC_TARGET_CPU + i * 4);

	set_handle_irq(a6_aic_handle_irq);
#ifdef CONFIG_SMP
	/* CPU1's hardware IPI gate must open before ARM's ipi_setup(cpu). */
	if (cpuhp_setup_state(CPUHP_AP_IRQ_APPLE_AIC_STARTING,
			      "irqchip/a6-aic:starting", a6_aic_starting_cpu,
			      NULL))
		return -ENODEV;
	base_ipi = ipi_mux_create(8, a6_aic_send_ipi);
	if (base_ipi <= 0)
		return -ENODEV;
	set_smp_ipi_range(base_ipi, 8);
#endif
	pr_info("A6 AIC: %u IRQs, CPU0 wired IRQ routing; IPI mux %s\n",
		nr_irqs, IS_ENABLED(CONFIG_SMP) ? "compiled" : "off");
	return 0;
}

IRQCHIP_DECLARE(apple_a6_aic, "apple,s5l8950-aic", a6_aic_init);

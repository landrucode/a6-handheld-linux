// SPDX-License-Identifier: GPL-2.0-only
/* One root-triggered, CPU0-owned integration proof. Storage survives timeout. */
#include <linux/completion.h>
#include <linux/mm.h>
#include <linux/vmalloc.h>
#include <linux/workqueue.h>
#include <asm/tlbflush.h>

static atomic_t a6_probe_attempted = ATOMIC_INIT(0);
static struct completion a6_probe_done;
static call_single_data_t a6_probe_csd;
static struct page *a6_probe_pages[2];
static struct vm_struct *a6_probe_area;
static u32 a6_probe_observed, a6_probe_expected;
static u32 a6_probe_calls, a6_probe_ranges, a6_probe_full, a6_probe_controls;
static int a6_probe_result = -EAGAIN;
static u32 a6_probe_phase;

static void a6_probe_read_cpu1(void *unused)
{
	WRITE_ONCE(a6_probe_observed,
		   a6_probe_phase == 1 ? smp_processor_id() :
		   READ_ONCE(*(u32 *)a6_probe_area->addr));
	WRITE_ONCE(a6_probe_calls, a6_probe_calls + 1);
	complete(&a6_probe_done);
}

static int a6_probe_read(void)
{
	int ret;

	reinit_completion(&a6_probe_done);
	INIT_CSD(&a6_probe_csd, a6_probe_read_cpu1, NULL);
	ret = smp_call_function_single_async(1, &a6_probe_csd);
	if (ret)
		return ret;
	/* Never reuse/free CSD, mapping or pages after a timed-out callback. */
	if (!wait_for_completion_timeout(&a6_probe_done, HZ))
		return -ETIMEDOUT;
	return 0;
}

static int a6_probe_set_pte(pte_t *pte, unsigned long addr, void *page)
{
	set_pte_at(&init_mm, addr, pte, mk_pte(page, PAGE_KERNEL));
	return 0;
}

static int a6_probe_map(unsigned int page)
{
	return apply_to_page_range(&init_mm, (unsigned long)a6_probe_area->addr,
				  PAGE_SIZE, a6_probe_set_pte, a6_probe_pages[page]);
}

static void a6_probe_work_fn(struct work_struct *work)
{
	unsigned long va;
	unsigned int i;
	int ret = -ENODEV;

	if (smp_processor_id() != 0 || !cpu_online(1) || !a6_smp_timer_ready(1))
		goto done;
	WRITE_ONCE(a6_probe_phase, 1);
	init_completion(&a6_probe_done);
	a6_probe_pages[0] = alloc_page(GFP_KERNEL | __GFP_ZERO);
	a6_probe_pages[1] = alloc_page(GFP_KERNEL | __GFP_ZERO);
	a6_probe_area = get_vm_area(PAGE_SIZE, VM_ALLOC);
	ret = -ENOMEM;
	if (!a6_probe_pages[0] || !a6_probe_pages[1] || !a6_probe_area)
		goto done;
	va = (unsigned long)a6_probe_area->addr;
	*(u32 *)page_address(a6_probe_pages[0]) = 0xa6c21111;
	*(u32 *)page_address(a6_probe_pages[1]) = 0xa6c22222;
	dsb(sy);
	ret = a6_probe_map(0);
	if (ret)
		goto done;
	/* Ping before any synchronous broadcast that could wait for an IPI. */
	ret = a6_probe_read();
	if (ret || a6_probe_observed != 1) {
		ret = ret ? ret : -EIO;
		goto done;
	}
	WRITE_ONCE(a6_probe_phase, 2);
	flush_tlb_kernel_range(va, va + PAGE_SIZE);
	for (i = 0; i < 32; i++) {
		/* Prime A, then change only the PTE: stale A is the negative control. */
		ret = a6_probe_map(0);
		if (ret)
			goto done;
		flush_tlb_kernel_range(va, va + PAGE_SIZE);
		ret = a6_probe_read();
		if (ret || a6_probe_observed != 0xa6c21111) {
			ret = ret ? ret : -EIO;
			goto done;
		}
		ret = a6_probe_map(1);
		if (ret)
			goto done;
		ret = a6_probe_read();
		if (ret || a6_probe_observed != 0xa6c21111) {
			/* No retained stale entry: the control is inconclusive, not PASS. */
			ret = ret ? ret : -ESTALE;
			goto done;
		}
		WRITE_ONCE(a6_probe_controls, i + 1);
		if (i & 1) {
			flush_tlb_all();
			WRITE_ONCE(a6_probe_full, a6_probe_full + 1);
		} else {
			flush_tlb_kernel_range(va, va + PAGE_SIZE);
			WRITE_ONCE(a6_probe_ranges, a6_probe_ranges + 1);
		}
		ret = a6_probe_read();
		WRITE_ONCE(a6_probe_expected, 0xa6c22222);
		if (ret || a6_probe_observed != a6_probe_expected) {
			ret = ret ? ret : -EIO;
			goto done;
		}
	}
	ret = 0;
done:
	WRITE_ONCE(a6_probe_result, ret);
	smp_store_release(&a6_probe_phase, ret ? 4 : 3);
	pr_info("A6 SMP shootdown: result=%d calls=%u controls=%u ranges=%u full=%u\n",
		ret, a6_probe_calls, a6_probe_controls, a6_probe_ranges, a6_probe_full);
	/* One virtual mapping and two pages deliberately retained until reboot. */
}
static DECLARE_WORK(a6_probe_work, a6_probe_work_fn);

static ssize_t a6_probe_store(struct kobject *kobj, struct kobj_attribute *attr,
			      const char *buf, size_t count)
{
	if (!sysfs_streq(buf, "prove"))
		return -EINVAL;
	if (!cpu_online(1) || !a6_smp_timer_ready(1))
		return -ENODEV;
	if (atomic_cmpxchg(&a6_probe_attempted, 0, 1))
		return -EALREADY;
	queue_work_on(0, system_percpu_wq, &a6_probe_work);
	return count;
}
static struct kobj_attribute a6_smp_probe_attr =
	__ATTR(probe, 0200, NULL, a6_probe_store);

static ssize_t a6_probe_status_show(struct kobject *kobj,
				  struct kobj_attribute *attr, char *buf)
{
	u32 phase = smp_load_acquire(&a6_probe_phase);
	return sysfs_emit(buf,
		"A6_SMP_SHOOTDOWN_V1 attempted=%d phase=%u result=%d calls=%u controls=%u ranges=%u full=%u observed=%08x expected=%08x\n",
		atomic_read(&a6_probe_attempted), phase, READ_ONCE(a6_probe_result),
		READ_ONCE(a6_probe_calls), READ_ONCE(a6_probe_controls),
		READ_ONCE(a6_probe_ranges), READ_ONCE(a6_probe_full),
		READ_ONCE(a6_probe_observed), READ_ONCE(a6_probe_expected));
}
static struct kobj_attribute a6_smp_probe_status_attr =
	__ATTR(probe_status, 0444, a6_probe_status_show, NULL);

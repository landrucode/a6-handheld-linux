// SPDX-License-Identifier: GPL-2.0-only
/* N42 one-shot Linux secondary handoff. First profile quarantines CPU1. */
#include <linux/delay.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kobject.h>
#include <linux/memblock.h>
#include <linux/of.h>
#include <linux/smp.h>
#include <linux/sysfs.h>

#include <asm/cacheflush.h>
#include <asm/cp15.h>
#include <asm/idmap.h>
#include <asm/memory.h>
#include <asm/pgtable.h>
#include <asm/smp.h>
#include <asm/smp_plat.h>
#include <asm/system_misc.h>

#include "a6-smp-layout.h"
#include "a6-smp-bridge-blob.h"

#if !defined(A6_SMP_QUARANTINE) && !defined(A6_SMP_SCHEDULING)
#error An explicit audited SMP profile is required
#endif
#ifdef A6_SMP_SCHEDULING
#define A6_SMP_IS_QUARANTINE 0
#define A6_SMP_STOP_STAGE 6
#else
#define A6_SMP_IS_QUARANTINE 1
#define A6_SMP_STOP_STAGE A6_SMP_STAGE_QUARANTINED
#endif

/* head.S uses this immutable, explicitly cleaned copy on this one boot.
 * __cpu_up() may clear its ordinary secondary_data after a timeout. */
struct secondary_data a6_smp_secondary_data __aligned(64);

static void __iomem *a6_smp_page, *a6_smp_pmgr;
static bool a6_smp_attempted, a6_smp_installed;
static int a6_smp_prepare_result = -ENODEV, a6_smp_boot_result = -EAGAIN;
static u32 a6_smp_alias_hash[2], a6_smp_vector_original[16];
static u32 a6_smp_pmgr_before[3], a6_smp_pmgr_after[3];
static u32 a6_smp_cpu0_prrr, a6_smp_cpu0_nmrr;

extern int a6_smp_timer_checkpoint_start(unsigned int cpu);
extern int a6_smp_timer_line_probe(void);
extern void a6_smp_timer_quiesce(void);
extern bool a6_smp_timer_ready(unsigned int cpu);
extern bool a6_smp_timer_prepared(void);
extern ssize_t a6_smp_timer_status(char *buf);

static void __iomem *a6_smp_marker(void)
{
	return a6_smp_page + 0x200;
}

static void a6_smp_stage(u32 value)
{
	dsb(sy);
	writel(value, a6_smp_marker() + A6_SMP_STAGE);
	dsb(sy);
}

/* CONFIG_CPU_IDLE=n alone does not remove the architecture's WFI default. */
static void a6_smp_awake_idle(void)
{
	cpu_relax();
}

static void __init a6_smp_prepare_cpus(unsigned int max_cpus)
{
	if (!of_machine_is_compatible("apple,n42ap") || PHYS_OFFSET != 0x80000000 ||
	    !memblock_is_region_memory(A6_SMP_VECTOR_PA, 0x2000) ||
	    memblock_is_map_memory(A6_SMP_VECTOR_PA) ||
	    memblock_is_map_memory(A6_SMP_VECTOR_PA + 0x1000) ||
	    !memblock_is_region_memory(A6_SMP_CODE_PA, PAGE_SIZE) ||
	    memblock_is_map_memory(A6_SMP_CODE_PA) || !(get_cr() & CR_V) ||
	    !a6_smp_timer_prepared())
		return;
	a6_smp_page = ioremap(A6_SMP_CODE_PA, PAGE_SIZE);
	a6_smp_pmgr = ioremap(0x3f101000, PAGE_SIZE);
	if (!a6_smp_page || !a6_smp_pmgr) {
		a6_smp_prepare_result = -ENOMEM;
		return;
	}
	asm volatile("mrc p15, 0, %0, c10, c2, 0" : "=r" (a6_smp_cpu0_prrr));
	asm volatile("mrc p15, 0, %0, c10, c2, 1" : "=r" (a6_smp_cpu0_nmrr));
	arm_pm_idle = a6_smp_awake_idle;
	a6_smp_prepare_result = 0;
	pr_info("A6 SMP: prepared one-shot bridge; hotplug/idle off, awake idle\n");
}

static int a6_smp_alias_and_install(void)
{
	void __iomem *ram, *zero;
	u32 word, other, hash;
	unsigned int page, i;
	int ret = -ENOMEM;

	ram = ioremap(A6_SMP_VECTOR_PA, 0x2000);
	zero = ioremap(0, 0x2000);
	if (!ram || !zero)
		goto done;
	/* Fresh full-page comparisons through Device mappings, before writing. */
	for (page = 0; page < 2; page++) {
		hash = 5381;
		for (i = 0; i < PAGE_SIZE; i += 4) {
			word = readl(ram + page * PAGE_SIZE + i);
			other = readl(zero + page * PAGE_SIZE + i);
			if (word != other) {
				ret = -ESTALE;
				goto done;
			}
			hash = hash * 33 ^ word;
		}
		a6_smp_alias_hash[page] = hash;
	}
	/* The tested reset-page alias gets a reversible fresh write check. */
	for (page = 0; page < 2; page++) {
		static const u32 patterns[] = { 0xa6c25a3c, 0x59e2a5c3 };
		word = readl(ram + page * PAGE_SIZE);
		for (i = 0; i < ARRAY_SIZE(patterns); i++) {
			writel(patterns[i], ram + page * PAGE_SIZE);
			dsb(sy);
			other = readl(zero + page * PAGE_SIZE);
			writel(word, ram + page * PAGE_SIZE);
			dsb(sy);
			if (other != patterns[i] || readl(zero + page * PAGE_SIZE) != word) {
				ret = -EIO;
				goto done;
			}
		}
	}
	for (i = 0; i < 16; i++)
		a6_smp_vector_original[i] = readl(ram + i * 4);
	for (i = 0; i < ARRAY_SIZE(a6_smp_bridge_blob); i++)
		writel(a6_smp_bridge_blob[i], a6_smp_page + i * 4);
	dsb(sy);
	for (i = 0; i < ARRAY_SIZE(a6_smp_bridge_blob); i++) {
		if (readl(a6_smp_page + i * 4) != a6_smp_bridge_blob[i]) {
			ret = -EIO;
			goto done;
		}
	}
	/* Publish literal destinations before the eight fixed ARM vectors. */
	for (i = 0; i < 8; i++)
		writel(i == 0 ? A6_SMP_CODE_PA : A6_SMP_EXCEPTION_PA,
		       ram + 0x20 + i * 4);
	for (i = 0; i < 8; i++)
		writel(0xe59ff018, ram + i * 4);
	dsb(sy);
	for (i = 0; i < 16; i++) {
		word = i < 8 ? 0xe59ff018 :
		       i == 8 ? A6_SMP_CODE_PA : A6_SMP_EXCEPTION_PA;
		if (readl(zero + i * 4) != word) {
			/* Before release only: restore the original reset page. */
			unsigned int j;
			for (j = 0; j < 16; j++)
				writel(a6_smp_vector_original[j], ram + j * 4);
			dsb(sy);
			ret = -EIO;
			goto done;
		}
	}
	a6_smp_installed = true;
	ret = 0;
done:
	if (zero)
		iounmap(zero);
	if (ram)
		iounmap(ram);
	return ret;
}

static int a6_smp_wait_stage(u32 expected, unsigned int usecs)
{
	u32 stage;
	unsigned int i;
	for (i = 0; i < usecs / 10; i++) {
		stage = readl(a6_smp_marker() + A6_SMP_STAGE);
		if (stage == expected)
			return 0;
		if (stage >= 0xf0)
			return -EPROTO;
		udelay(10);
	}
	return -ETIMEDOUT;
}

static int a6_smp_boot_secondary(unsigned int cpu, struct task_struct *idle)
{
	void __iomem *marker;
	u32 target, *words;
	unsigned int i;
	int ret;

	if (cpu != 1 || cpu_logical_map(cpu) != 1 || a6_smp_prepare_result)
		return -EPERM;
	if (a6_smp_attempted)
		return -EALREADY;
	a6_smp_attempted = true;
	marker = a6_smp_marker();
	for (i = 0; i < 48; i++)
		writel(0, marker + i * 4);
	ret = a6_smp_alias_and_install();
	if (ret)
		goto finish;
	BUILD_BUG_ON(offsetof(struct secondary_data, stack) != 12);
	BUILD_BUG_ON(offsetof(struct secondary_data, task) != 16);
	a6_smp_secondary_data = secondary_data;
	sync_cache_w(&a6_smp_secondary_data);
	/* Explicit PoC clean matches the maintained cache-probe control. */
	words = (u32 *)&a6_smp_secondary_data;
	for (i = 0; i < sizeof(a6_smp_secondary_data); i += 32)
		asm volatile("mcr p15, 0, %0, c7, c10, 1" : :
			     "r" ((unsigned long)words + i) : "memory");
	__cpuc_flush_dcache_area(idmap_pgd, PTRS_PER_PGD * sizeof(pgd_t));
	dsb(sy);
	/* ELF FUNC is Thumb-tagged by ENDPROC despite the ARM veneer.
	 * Build audit verifies the eight-byte ARM entry before clearing bit 0. */
	target = __pa_symbol(secondary_startup_arm) & ~1U;
	if (target < 0x80008000 || target >= 0x80800000 || (target & 3)) {
		ret = -ERANGE;
		goto finish;
	}
	writel(target, marker + A6_SMP_TARGET);
	writel(__pa_symbol(&a6_smp_secondary_data), marker + A6_SMP_SHADOW_PA);
	for (i = 0; i < 5; i++)
		writel(words[i], marker + A6_SMP_EXPECT_DATA + i * 4);
	writel(1, marker + A6_SMP_GO); /* waiting; zero always means cancel */
	dsb(sy);
	a6_smp_pmgr_before[0] = readl(a6_smp_pmgr + 0x210);
	a6_smp_pmgr_before[1] = readl(a6_smp_pmgr + 0x214);
	a6_smp_pmgr_before[2] = readl(a6_smp_pmgr + 0x220);
	writel(2, a6_smp_pmgr + 0x214);
	dsb(sy);
	writel(2, a6_smp_pmgr + 0x220);
	dsb(sy);
	ret = a6_smp_wait_stage(A6_SMP_STAGE_READY, 500000);
	if (ret)
		goto finish;
	writel(A6_SMP_GO_MAGIC, marker + A6_SMP_GO);
	dsb(sy);
	sev();
	ret = a6_smp_wait_stage(A6_SMP_STOP_STAGE, 500000);
finish:
	/* A timeout revokes entry; immutable shadow remains valid for late fetch. */
	writel(0, marker + A6_SMP_GO);
	dsb(sy);
	sev();
	a6_smp_pmgr_after[0] = readl(a6_smp_pmgr + 0x210);
	a6_smp_pmgr_after[1] = readl(a6_smp_pmgr + 0x214);
	a6_smp_pmgr_after[2] = readl(a6_smp_pmgr + 0x220);
	a6_smp_boot_result = ret;
	pr_info("A6 SMP bridge: result=%d stage=%u target=%08x quarantine=%u\n",
		ret, readl(marker + A6_SMP_STAGE), readl(marker + A6_SMP_TARGET),
		A6_SMP_IS_QUARANTINE);
	/* Expected quarantine pass returns an error to keep CPU1 offline. */
	return ret ? ret : (A6_SMP_IS_QUARANTINE ? -ECANCELED : 0);
}

static const struct smp_operations a6_smp_ops __initconst = {
	.smp_prepare_cpus = a6_smp_prepare_cpus,
	.smp_boot_secondary = a6_smp_boot_secondary,
};
CPU_METHOD_OF_DECLARE(a6_swift_smp, "apple,a6-one-shot", &a6_smp_ops);

/* Called before notify_cpu_starting(): never join RCU or online masks. */
void a6_smp_secondary_checkpoint(unsigned int cpu);
void a6_smp_secondary_checkpoint(unsigned int cpu)
{
	void __iomem *marker = a6_smp_marker();
	u32 sctlr, prrr, nmrr, cntfrq;
	u64 before, after;
	unsigned int i;
	int result = 0;

	a6_smp_stage(A6_SMP_STAGE_KERNEL);
	asm volatile("cpsid if" : : : "memory");
	#ifndef A6_SMP_SCHEDULING
#ifdef A6_SMP_TIMER_LINE_PROBE
	result = a6_smp_timer_line_probe();
#endif
	if (!result)
		result = a6_smp_timer_checkpoint_start(cpu);
	a6_smp_timer_quiesce();
#endif
	{ u32 value; asm volatile("mrc p15, 0, %0, c2, c0, 0" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_TTBR0); }
	{ u32 value; asm volatile("mrc p15, 0, %0, c2, c0, 1" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_TTBR1); }
	{ u32 value; asm volatile("mrc p15, 0, %0, c2, c0, 2" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_TTBCR); }
	{ u32 value; asm volatile("mrc p15, 0, %0, c3, c0, 0" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_DACR); }
	{ u32 value; asm volatile("mrc p15, 0, %0, c13, c0, 1" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_CONTEXTIDR); }
	{ u32 value; asm volatile("mov %0, pc" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_PC); }
	{ u32 value; asm volatile("mov %0, sp" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_SP); }
	{ u32 value; asm volatile("mrs %0, cpsr" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_CPSR); }
	{ u32 value; asm volatile("mrc p15, 0, %0, c14, c3, 1" : "=r" (value));
	  writel(value, marker + A6_SMP_KERNEL_TIMER_CTL); }

	sctlr = get_cr();
	asm volatile("mrc p15, 0, %0, c10, c2, 0" : "=r" (prrr));
	asm volatile("mrc p15, 0, %0, c10, c2, 1" : "=r" (nmrr));
	asm volatile("mrc p15, 0, %0, c14, c0, 0" : "=r" (cntfrq));
	asm volatile("isb; mrrc p15, 0, %Q0, %R0, c14" : "=r" (before));
	for (i = 0; i < 1000; i++)
		cpu_relax();
	asm volatile("isb; mrrc p15, 0, %Q0, %R0, c14" : "=r" (after));
	writel(sctlr, marker + A6_SMP_KERNEL_SCTLR);
	writel(prrr, marker + A6_SMP_KERNEL_PRRR);
	writel(nmrr, marker + A6_SMP_KERNEL_NMRR);
	writel(cntfrq, marker + A6_SMP_KERNEL_CNTFRQ);
	writel(lower_32_bits(before), marker + A6_SMP_COUNTER0);
	writel(upper_32_bits(before), marker + A6_SMP_COUNTER0 + 4);
	writel(lower_32_bits(after), marker + A6_SMP_COUNTER1);
	writel(upper_32_bits(after), marker + A6_SMP_COUNTER1 + 4);
	writel(a6_smp_timer_ready(cpu), marker + A6_SMP_TIMER_READY);
	if (cpu != 1 || (sctlr & (CR_M | CR_C | CR_I | CR_V)) !=
	    (CR_M | CR_C | CR_I | CR_V) || prrr != a6_smp_cpu0_prrr ||
	    nmrr != a6_smp_cpu0_nmrr || cntfrq != 24000000 || after <= before ||
	    !(A6_SMP_IS_QUARANTINE ? a6_smp_timer_ready(cpu) : a6_smp_timer_prepared()))
		result = -EPROTO;
	if (readl(marker + A6_SMP_GO) != A6_SMP_GO_MAGIC)
		result = -ECANCELED;
	writel(result, marker + A6_SMP_RESULT);
	a6_smp_stage(result ? A6_SMP_STAGE_KERNEL_BAD : A6_SMP_STOP_STAGE);
#ifdef A6_SMP_SCHEDULING
	if (!result)
		return; /* Continue normal RCU, AIC/timer callbacks and online path. */
#endif
	/* IRQ/FIQ remain masked. No normal task, hotplug or WFI on CPU1. */
	for (;;)
		wfe();
}

static ssize_t a6_smp_status_show(struct kobject *kobj,
				struct kobj_attribute *attr, char *buf)
{
	void __iomem *m;
	ssize_t used;
	unsigned int i;

	if (!a6_smp_page)
		return sysfs_emit(buf, "A6_SMP_BRIDGE_V1 prepare_result=%d attempted=0\n",
				 a6_smp_prepare_result);
	m = a6_smp_marker();
	used = sysfs_emit(buf,
		"A6_SMP_BRIDGE_V1 prepare_result=%d attempted=%u installed=%u result=%d quarantine=%u stage=%u magic=%08x target=%08x shadow_pa=%08x\n"
		"entry_sctlr=%08x mpidr=%08x cpsr=%08x midr=%08x pfr1=%08x\n"
		"kernel_sctlr=%08x prrr=%08x nmrr=%08x cntfrq=%u timer_ready=%u checkpoint_result=%d exception=%08x\n"
		"counter_before=%08x%08x counter_after=%08x%08x\n"
		"alias_hash=%08x/%08x pmgr_before=%08x/%08x/%08x pmgr_after=%08x/%08x/%08x\n",
		a6_smp_prepare_result, a6_smp_attempted, a6_smp_installed,
		a6_smp_boot_result, A6_SMP_IS_QUARANTINE, readl(m + A6_SMP_STAGE), readl(m + A6_SMP_SIGNATURE),
		readl(m + A6_SMP_TARGET), readl(m + A6_SMP_SHADOW_PA),
		readl(m + A6_SMP_ENTRY_SCTLR), readl(m + A6_SMP_MPIDR),
		readl(m + A6_SMP_CPSR), readl(m + A6_SMP_MIDR), readl(m + A6_SMP_PFR1),
		readl(m + A6_SMP_KERNEL_SCTLR), readl(m + A6_SMP_KERNEL_PRRR),
		readl(m + A6_SMP_KERNEL_NMRR), readl(m + A6_SMP_KERNEL_CNTFRQ),
		readl(m + A6_SMP_TIMER_READY), (int)readl(m + A6_SMP_RESULT),
		readl(m + A6_SMP_EXCEPTION),
		readl(m + A6_SMP_COUNTER0 + 4), readl(m + A6_SMP_COUNTER0),
		readl(m + A6_SMP_COUNTER1 + 4), readl(m + A6_SMP_COUNTER1),
		a6_smp_alias_hash[0], a6_smp_alias_hash[1],
		a6_smp_pmgr_before[0], a6_smp_pmgr_before[1], a6_smp_pmgr_before[2],
		a6_smp_pmgr_after[0], a6_smp_pmgr_after[1], a6_smp_pmgr_after[2]);
	used += sysfs_emit_at(buf, used, "ttbr0=%08x ttbr1=%08x ttbcr=%08x dacr=%08x contextidr=%08x pc=%08x sp=%08x parked_cpsr=%08x timer_ctl=%08x\n",
		readl(m + A6_SMP_KERNEL_TTBR0),
		readl(m + A6_SMP_KERNEL_TTBR1),
		readl(m + A6_SMP_KERNEL_TTBCR),
		readl(m + A6_SMP_KERNEL_DACR),
		readl(m + A6_SMP_KERNEL_CONTEXTIDR),
		readl(m + A6_SMP_KERNEL_PC),
		readl(m + A6_SMP_KERNEL_SP),
		readl(m + A6_SMP_KERNEL_CPSR),
		readl(m + A6_SMP_KERNEL_TIMER_CTL));
	for (i = 0; i < 5; i++)
		used += sysfs_emit_at(buf, used, "handoff_word%u=%08x/%08x\n", i,
			readl(m + A6_SMP_EXPECT_DATA + i * 4),
			readl(m + A6_SMP_OBSERVED_DATA + i * 4));
	return used;
}

static struct kobj_attribute a6_smp_status_attr =
	__ATTR(status, 0444, a6_smp_status_show, NULL);
static ssize_t a6_smp_timer_show(struct kobject *kobj,
			       struct kobj_attribute *attr, char *buf)
{
	return a6_smp_timer_status(buf);
}
static struct kobj_attribute a6_smp_timer_attr =
	__ATTR(timer, 0444, a6_smp_timer_show, NULL);
#ifdef A6_SMP_SCHEDULING
#include "a6-smp-shootdown.inc"
#endif

static struct attribute *a6_smp_attrs[] = {
#ifdef A6_SMP_SCHEDULING
	&a6_smp_probe_attr.attr, &a6_smp_probe_status_attr.attr,
#endif
	&a6_smp_status_attr.attr, &a6_smp_timer_attr.attr, NULL,
};
static const struct attribute_group a6_smp_group = {
	.name = "a6_smp_bridge", .attrs = a6_smp_attrs,
};

static int __init a6_smp_status_init(void)
{
	return sysfs_create_group(firmware_kobj, &a6_smp_group);
}
late_initcall(a6_smp_status_init);

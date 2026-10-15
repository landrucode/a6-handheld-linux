// SPDX-License-Identifier: GPL-2.0-only
/* N42-only bring-up PHY: sequence verified against iBEC and USB proofs.
 * Owns only the three USB PMGR gates and USB PHY; never touches storage.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/phy/phy.h>

struct a6_usb_phy {
	void __iomem *phy, *pmgr, *pcgc;
};

static int a6_usb_power_on(struct phy *phy)
{
	struct a6_usb_phy *a = phy_get_drvdata(phy);
	static const u32 gates[] = { 0x84, 0x88, 0x9c };
	u32 v;
	int i, ret;

	msleep(10);
	for (i = 0; i < ARRAY_SIZE(gates); i++) {
		writel(readl(a->pmgr + gates[i]) | 0xf, a->pmgr + gates[i]);
		ret = readl_poll_timeout(a->pmgr + gates[i], v,
					(v & 0xff) == 0xff, 1, 100000);
		if (ret)
			return ret;
	}
	/* Shared DWC2 clock-stop register, before the core is initialized. */
	writel(readl(a->pcgc) & ~3, a->pcgc);
	udelay(100);
	writel(0x200, a->phy + 0x60);
	writel(6, a->phy);
	writel(4, a->phy + 0x1c);
	writel(0x749, a->phy + 0x40);
	writel(0x2ff3, a->phy + 0x44);
	udelay(10);
	writel((readl(a->phy + 4) & ~3) | 1, a->phy + 4);
	writel(readl(a->phy + 8) | 1, a->phy + 8);
	udelay(20);
	writel(readl(a->phy + 8) & ~1, a->phy + 8);
	usleep_range(1000, 2000);
	/* Firmware attach gate: DWC2 retains ownership of soft-disconnect. */
	writel(readl(a->phy + 0x1c) | 2, a->phy + 0x1c);
	if (readl(a->phy) != 6 || (readl(a->phy + 8) & 1) ||
	    readl(a->phy + 0x1c) != 6)
		return -EIO;
	dev_info(&phy->dev, "A6 USB PHY ready: UVLDCON=6, PIO gadget\n");
	return 0;
}

static int a6_usb_power_off(struct phy *phy)
{
	struct a6_usb_phy *a = phy_get_drvdata(phy);

	writel(readl(a->phy + 0x1c) & ~2, a->phy + 0x1c);
	writel(0x1f, a->phy);
	writel(readl(a->phy + 8) | 1, a->phy + 8);
	/* Leave gates on: no unverified shared-clock shutdown. */
	return 0;
}

static const struct phy_ops a6_usb_ops = {
	.power_on = a6_usb_power_on,
	.power_off = a6_usb_power_off,
	.owner = THIS_MODULE,
};

static int a6_usb_phy_probe(struct platform_device *pdev)
{
	struct a6_usb_phy *a;
	struct phy_provider *provider;
	struct phy *phy;
	struct resource *res;

	a = devm_kzalloc(&pdev->dev, sizeof(*a), GFP_KERNEL);
	if (!a)
		return -ENOMEM;
	a->phy = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(a->phy))
		return PTR_ERR(a->phy);
	a->pmgr = devm_platform_ioremap_resource(pdev, 1);
	if (IS_ERR(a->pmgr))
		return PTR_ERR(a->pmgr);
	/* DWC2 reserves the encompassing core resource; do not reserve twice. */
	res = platform_get_resource(pdev, IORESOURCE_MEM, 2);
	if (!res || resource_size(res) != 4)
		return -EINVAL;
	a->pcgc = devm_ioremap(&pdev->dev, res->start, resource_size(res));
	if (!a->pcgc)
		return -ENOMEM;
	phy = devm_phy_create(&pdev->dev, NULL, &a6_usb_ops);
	if (IS_ERR(phy))
		return PTR_ERR(phy);
	phy_set_drvdata(phy, a);
	provider = devm_of_phy_provider_register(&pdev->dev, of_phy_simple_xlate);
	return PTR_ERR_OR_ZERO(provider);
}

static const struct of_device_id a6_usb_phy_match[] = {
	{ .compatible = "apple,s5l8950-usb-phy" }, { }
};
MODULE_DEVICE_TABLE(of, a6_usb_phy_match);
static struct platform_driver a6_usb_phy_driver = {
	.probe = a6_usb_phy_probe,
	.driver = { .name = "a6-usb-phy", .of_match_table = a6_usb_phy_match },
};
module_platform_driver(a6_usb_phy_driver);
MODULE_LICENSE("GPL");

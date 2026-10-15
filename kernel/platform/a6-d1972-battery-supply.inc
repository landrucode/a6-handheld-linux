// SPDX-License-Identifier: GPL-2.0-only
/* Cached VBAT only. A reading is available after a successful guarded sample.
 * Do not claim SOC, charging status or charge current from this voltage.
 */
static enum power_supply_property a6_battery_properties[] = {
	POWER_SUPPLY_PROP_VOLTAGE_NOW,
};

static int a6_battery_get_property(struct power_supply *psy,
		enum power_supply_property property,
		union power_supply_propval *value)
{
	int ret = 0;

	if (property != POWER_SUPPLY_PROP_VOLTAGE_NOW)
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	if (!a6_vbat_samples || a6_vbat_result || !a6_vbat_restored)
		ret = -ENODATA;
	else
		value->intval = 2500000 + (u64)a6_vbat_raw * 32000000 / 65536;
	mutex_unlock(&a6_touch_lock);
	return ret;
}

static const struct power_supply_desc a6_battery_desc = {
	.name = "a6-d1972-battery",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = a6_battery_properties,
	.num_properties = ARRAY_SIZE(a6_battery_properties),
	.get_property = a6_battery_get_property,
};

static int __init a6_battery_supply_init(void)
{
	struct platform_device *pdev;
	struct power_supply *psy;

	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c)
		return -ENODEV;
	pdev = platform_device_register_simple("a6-d1972-battery", -1, NULL, 0);
	if (IS_ERR(pdev))
		return PTR_ERR(pdev);
	psy = devm_power_supply_register(&pdev->dev, &a6_battery_desc, NULL);
	if (IS_ERR(psy)) {
		int ret = PTR_ERR(psy);
		platform_device_unregister(pdev);
		return ret;
	}
	return 0;
}
late_initcall(a6_battery_supply_init);

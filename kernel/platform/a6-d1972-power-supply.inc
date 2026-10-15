// SPDX-License-Identifier: GPL-2.0-only
/* First persistent D1972 power_supply property: live USB input-limit setting.
 * This says nothing about VBUS presence or measured charge into the battery.
 * The standard I2C adapter and USB/HDQ inputs still need platform drivers.
 */
static enum power_supply_property a6_d1972_properties[] = {
	POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,
#ifdef A6_D1972_POLICY
	POWER_SUPPLY_PROP_ONLINE,
#endif
};

#ifdef A6_D1972_POLICY
/* Defined by the guarded policy later in this generated translation unit. */
static int a6_policy_adc(u8 channel, unsigned int *raw);
#endif

static int a6_d1972_get_property(struct power_supply *psy,
		enum power_supply_property property,
		union power_supply_propval *value)
{
	u8 code;
	int ret;

	if (property != POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT
#ifdef A6_D1972_POLICY
	    && property != POWER_SUPPLY_PROP_ONLINE
#endif
	   )
		return -EINVAL;
	mutex_lock(&a6_touch_lock);
	ret = a6_power_validate();
	if (!ret) {
#ifdef A6_D1972_POLICY
		if (property == POWER_SUPPLY_PROP_ONLINE) {
			unsigned int raw;

			ret = a6_policy_adc(15, &raw);
			if (!ret) {
				unsigned int mv = (u32)((u64)raw * 88000 / 65536);

				value->intval = mv >= 4400 && mv <= 5500;
			}
		} else
#endif
			ret = a6_power_xfer(0x43, &code, false, false);
	}
	if (ret)
		a6_power_recover();
	mutex_unlock(&a6_touch_lock);
	if (ret)
		return ret;
	if (property == POWER_SUPPLY_PROP_ONLINE)
		return 0;
	/* AppleD1972PMU maps the six-bit code in 30 mA steps. */
	value->intval = (code & 0x3f) * 30000;
	return 0;
}

static const struct power_supply_desc a6_d1972_desc = {
	.name = "a6-d1972-usb",
	.type = POWER_SUPPLY_TYPE_USB,
	.properties = a6_d1972_properties,
	.num_properties = ARRAY_SIZE(a6_d1972_properties),
	.get_property = a6_d1972_get_property,
};

static int __init a6_d1972_power_supply_init(void)
{
	struct platform_device *pdev;
	struct power_supply *psy;

	if (!of_machine_is_compatible("apple,n42ap") || !a6_touch_i2c)
		return -ENODEV;
	pdev = platform_device_register_simple("a6-d1972-power", -1, NULL, 0);
	if (IS_ERR(pdev))
		return PTR_ERR(pdev);
	psy = devm_power_supply_register(&pdev->dev, &a6_d1972_desc, NULL);
	if (IS_ERR(psy)) {
		int ret = PTR_ERR(psy);
		platform_device_unregister(pdev);
		return ret;
	}
	return 0;
}
late_initcall(a6_d1972_power_supply_init);

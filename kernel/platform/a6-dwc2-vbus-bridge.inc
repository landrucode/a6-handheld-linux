/* N42 diagnostic: drive the UDC session from the D1972 USB-source reading.
 * This remains opt-in until a long source-change trial validates it.
 */
#include <linux/power_supply.h>
#include <linux/workqueue.h>

static struct dwc2_hsotg *a6_vbus_hsotg;
static struct delayed_work a6_vbus_work;
static bool a6_vbus_stopping;
static int a6_vbus_pending = -1;
static int a6_vbus_confirmed = -1;
static unsigned int a6_vbus_streak;

#ifdef A6_USB_VBUS_AUTO_RECOVER
extern int a6_usb_udc_cycle(struct usb_gadget *gadget);
static struct delayed_work a6_vbus_recover_work;

static void a6_vbus_recover_tick(struct work_struct *work)
{
	struct power_supply *psy;
	union power_supply_propval value;
	unsigned long flags;
	u32 gotgctl, gintmsk;
	int ret;

	if (READ_ONCE(a6_vbus_stopping) ||
	    READ_ONCE(a6_vbus_confirmed) != 1)
		return;
	psy = power_supply_get_by_name("a6-d1972-usb");
	if (!psy)
		return;
	ret = power_supply_get_property(psy, POWER_SUPPLY_PROP_ONLINE, &value);
	power_supply_put(psy);
	if (ret || value.intval != 1)
		return;

	spin_lock_irqsave(&a6_vbus_hsotg->lock, flags);
	gotgctl = dwc2_readl(a6_vbus_hsotg, GOTGCTL);
	gintmsk = dwc2_readl(a6_vbus_hsotg, GINTMSK);
	spin_unlock_irqrestore(&a6_vbus_hsotg->lock, flags);
	if ((gotgctl & GOTGCTL_BSESVLD) ||
	    (gintmsk & (GINTSTS_USBRST | GINTSTS_ENUMDONE)) ==
	    (GINTSTS_USBRST | GINTSTS_ENUMDONE))
		return;

	dev_warn(a6_vbus_hsotg->dev,
		 "A6 USB recovery: invalid session gotgctl=%08x gintmsk=%08x\n",
		 gotgctl, gintmsk);
	ret = a6_usb_udc_cycle(&a6_vbus_hsotg->gadget);
	dev_info(a6_vbus_hsotg->dev, "A6 USB recovery: UDC cycle result=%d\n",
		 ret);
}
#endif

#ifdef A6_USB_BVALID_OVERRIDE
/* Diagnostic: derive DWC2 B-session validity from the guarded PMU source. */
static bool a6_vbus_set_bvalid(struct dwc2_hsotg *hsotg, bool online)
{
	unsigned long flags;
	u32 old, next, actual;

	spin_lock_irqsave(&hsotg->lock, flags);
	old = dwc2_readl(hsotg, GOTGCTL);
	next = old | GOTGCTL_BVALOEN | GOTGCTL_VBVALOEN |
		GOTGCTL_DBNCE_FLTR_BYPASS;
	next &= ~(GOTGCTL_BVALOVAL | GOTGCTL_VBVALOVAL);
	if (online)
		next |= GOTGCTL_BVALOVAL | GOTGCTL_VBVALOVAL;
	if (next != old)
		dwc2_writel(hsotg, next, GOTGCTL);
	actual = dwc2_readl(hsotg, GOTGCTL);
	spin_unlock_irqrestore(&hsotg->lock, flags);

	if (next != old)
		dev_info(hsotg->dev,
			 "A6 BVALID override: source=%u before=%08x wrote=%08x read=%08x\n",
			 online, old, next, actual);
	if ((actual & (GOTGCTL_BVALOEN | GOTGCTL_VBVALOEN |
		       GOTGCTL_DBNCE_FLTR_BYPASS |
		       GOTGCTL_BVALOVAL | GOTGCTL_VBVALOVAL)) !=
	    (next & (GOTGCTL_BVALOEN | GOTGCTL_VBVALOEN |
		     GOTGCTL_DBNCE_FLTR_BYPASS |
		     GOTGCTL_BVALOVAL | GOTGCTL_VBVALOVAL))) {
		dev_warn_ratelimited(hsotg->dev,
			"A6 BVALID override bits did not latch: wrote=%08x read=%08x\n",
			next, actual);
		return false;
	}
	if (!!(actual & GOTGCTL_BSESVLD) != online) {
		dev_warn_ratelimited(hsotg->dev,
			"A6 BVALID override mismatch: source=%u gotgctl=%08x\n",
			online, actual);
		return false;
	}
	return true;
}
#endif

static void a6_vbus_bridge_tick(struct work_struct *work)
{
	struct power_supply *psy;
	union power_supply_propval value;
	int ret = -ENODEV;

	psy = power_supply_get_by_name("a6-d1972-usb");
	if (psy) {
		ret = power_supply_get_property(psy, POWER_SUPPLY_PROP_ONLINE,
						&value);
		power_supply_put(psy);
	}
	if (!ret && (value.intval == 0 || value.intval == 1)) {
		if (value.intval != a6_vbus_pending) {
			a6_vbus_pending = value.intval;
			a6_vbus_streak = 1;
		} else if (a6_vbus_streak < 2) {
			a6_vbus_streak++;
		}
		if (a6_vbus_streak == 2 &&
		    a6_vbus_confirmed != a6_vbus_pending) {
			#ifdef A6_USB_BVALID_OVERRIDE
			if (!a6_vbus_set_bvalid(a6_vbus_hsotg,
						 a6_vbus_pending))
				goto next_tick;
			#endif
			a6_vbus_confirmed = a6_vbus_pending;
			#ifdef A6_USB_VBUS_AUTO_RECOVER
			cancel_delayed_work(&a6_vbus_recover_work);
			#endif
			usb_udc_vbus_handler(&a6_vbus_hsotg->gadget,
					     a6_vbus_confirmed);
			dev_info(a6_vbus_hsotg->dev,
				 "A6 VBUS bridge: source=%d\n",
				 a6_vbus_confirmed);
			#ifdef A6_USB_VBUS_AUTO_RECOVER
			if (a6_vbus_confirmed == 1)
				schedule_delayed_work(&a6_vbus_recover_work,
					      15 * HZ);
			#endif
		}
	} else {
		/* A failed sample cannot manufacture an attach or detach edge. */
		a6_vbus_pending = -1;
		a6_vbus_streak = 0;
	}
#ifdef A6_USB_BVALID_OVERRIDE
next_tick:
#endif
	if (!READ_ONCE(a6_vbus_stopping))
		schedule_delayed_work(&a6_vbus_work, HZ);
}

static void a6_vbus_bridge_start(struct dwc2_hsotg *hsotg)
{
	if (!of_device_is_compatible(hsotg->dev->of_node,
				     "apple,s5l8950-dwc2"))
		return;
	a6_vbus_hsotg = hsotg;
	WRITE_ONCE(a6_vbus_stopping, false);
	a6_vbus_pending = -1;
	a6_vbus_confirmed = -1;
	a6_vbus_streak = 0;
	INIT_DELAYED_WORK(&a6_vbus_work, a6_vbus_bridge_tick);
	#ifdef A6_USB_VBUS_AUTO_RECOVER
	INIT_DELAYED_WORK(&a6_vbus_recover_work, a6_vbus_recover_tick);
	#endif
	schedule_delayed_work(&a6_vbus_work, HZ);
}

static void a6_vbus_bridge_stop(struct dwc2_hsotg *hsotg)
{
	if (a6_vbus_hsotg != hsotg)
		return;
	WRITE_ONCE(a6_vbus_stopping, true);
	cancel_delayed_work_sync(&a6_vbus_work);
	#ifdef A6_USB_VBUS_AUTO_RECOVER
	cancel_delayed_work_sync(&a6_vbus_recover_work);
	#endif
	a6_vbus_hsotg = NULL;
}

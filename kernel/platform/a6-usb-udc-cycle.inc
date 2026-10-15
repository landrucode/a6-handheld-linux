/* N42 attended candidate: perform the same guarded UDC stop/start as
 * soft_connect=disconnect, then soft_connect=connect. Workqueue context only.
 */
int a6_usb_udc_cycle(struct usb_gadget *gadget)
{
	struct usb_udc *udc;
	int ret;

	if (!gadget)
		return -EINVAL;
	device_lock(&gadget->dev);
	udc = gadget->udc;
	if (!udc) {
		ret = -ENODEV;
		goto unlock_device;
	}
	mutex_lock(&udc->connect_lock);
	if (!udc->driver || !udc->started || !udc->vbus ||
	    !gadget->connected) {
		ret = -ENODEV;
		goto unlock_connect;
	}
	ret = usb_gadget_disconnect_locked(gadget);
	if (ret)
		goto unlock_connect;
	usb_gadget_udc_stop_locked(udc);
	msleep(1000);
	ret = usb_gadget_udc_start_locked(udc);
	if (ret)
		goto unlock_connect;
	if (udc->vbus && udc->allow_connect)
		ret = usb_gadget_connect_locked(gadget);

unlock_connect:
	mutex_unlock(&udc->connect_lock);
unlock_device:
	device_unlock(&gadget->dev);
	return ret;
}
EXPORT_SYMBOL_GPL(a6_usb_udc_cycle);

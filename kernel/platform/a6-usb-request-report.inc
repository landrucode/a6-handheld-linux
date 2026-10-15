
/* Probe outcomes and passive USB state. Never read FIFO-pop or AIC EVENT. */
unsigned int a6_usb_diag[12] = { [1] = 0x7fffffff, [3] = 0x7fffffff, [5] = 0x7fffffff };
extern u32 a6_usb_aic_read(u32 offset);
extern void a6_diag_timer_row(unsigned int row, const char *text);
static struct dwc2_hsotg *a6_report_hsotg;
static unsigned int a6_report_count;
static void a6_usb_report_work(struct work_struct *work);
static DECLARE_DELAYED_WORK(a6_usb_report_job, a6_usb_report_work);

static void usb_report_row(unsigned int row, const char *name, u32 value)
{
    char text[26];
    unsigned int i;
    for (i = 0; i < 25; i++) text[i] = ' ';
    text[25] = 0;
    for (i = 0; i < 16 && name[i]; i++) text[i] = name[i];
    for (i = 0; i < 8; i++) text[17+i] = "0123456789ABCDEF"[(value >> (28-4*i)) & 15];
    a6_diag_timer_row(row, text);
}

static void a6_usb_report_work(struct work_struct *work)
{
    struct dwc2_hsotg *h = READ_ONCE(a6_report_hsotg);
    bool powered = h && h->ll_hw_enabled;
    const u32 regs[] = { GSNPSID, GAHBCFG, GINTSTS, GINTMSK, DCTL, DCFG, DSTS, DAINT, DAINTMSK };
    const char *names[] = { "GSNPSID", "GAHBCFG", "GINTSTS", "GINTMSK", "DCTL", "DCFG", "DSTS", "DAINT", "DAINTMSK" };
    u32 values[9], i;
    /* Reads of these status registers do not acknowledge or pop requests.
     * Boot-only diagnostic: successful device remains bound for this run. */
    for (i = 0; i < 9; i++) values[i] = powered ? dwc2_readl(h, regs[i]) : 0xfffffffe;
    usb_report_row(0, "USB REPORT", ++a6_report_count);
    usb_report_row(1, "PROBE STAGE", READ_ONCE(a6_usb_diag[0]));
    usb_report_row(2, "PROBE RETURN", READ_ONCE(a6_usb_diag[1]));
    usb_report_row(3, "PHY ON CALLS", READ_ONCE(a6_usb_diag[2]));
    usb_report_row(4, "PHY RETURN", READ_ONCE(a6_usb_diag[3]));
    usb_report_row(5, "SERIAL BIND RET", READ_ONCE(a6_usb_diag[5]));
    usb_report_row(6, "AIC USB EVENTS", READ_ONCE(a6_usb_diag[6]));
    usb_report_row(7, "GADGET IRQ CALLS", READ_ONCE(a6_usb_diag[7]));
    usb_report_row(8, "SETUP REQUESTS", READ_ONCE(a6_usb_diag[8]));
    usb_report_row(9, "LAST SETUP", READ_ONCE(a6_usb_diag[9]));
    usb_report_row(10, "CORE POWERED", powered);
    usb_report_row(11, "AIC HW BANK 0", a6_usb_aic_read(0x4200));
    usb_report_row(12, "AIC MASK BANK 0", a6_usb_aic_read(0x4100));
    usb_report_row(13, "USB TARGET", a6_usb_aic_read(0x302c));
    for (i = 0; i < 9; i++) usb_report_row(14+i, names[i], values[i]);
    usb_report_row(23, "EP0 STATE", h ? READ_ONCE(h->ep0_state) : ~0U);
    if (a6_report_count < 60) schedule_delayed_work(&a6_usb_report_job, HZ);
}

static int dwc2_driver_probe(struct platform_device *dev)
{
    int ret = dwc2_driver_probe_impl(dev);
    a6_usb_diag[1] = ret;
    if (!ret) {
        a6_usb_diag[0] = 10;
        WRITE_ONCE(a6_report_hsotg, platform_get_drvdata(dev));
    }
    schedule_delayed_work(&a6_usb_report_job, 2 * HZ);
    return ret;
}

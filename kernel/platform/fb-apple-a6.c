// SPDX-License-Identifier: GPL-2.0-only
/* Transitional fbdev access to the framebuffer inherited from n42 iBEC.
 * No display-controller, clock, panel or power-register programming.
 * The diagnostic boot path owns a permanent strongly-ordered identity map;
 * reuse it and require identical attributes for userspace mappings.
 */
#include <linux/fb.h>
#include <linux/init.h>
#include <linux/ioport.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <asm/pgtable.h>
#ifdef A6_DIRECT_DRM
#include <linux/platform_data/simplefb.h>
#endif

extern u32 a6_fb_base_saved, a6_fb_words_saved, a6_fb_stride_saved;

static bool a6_fb_mapping_valid(unsigned long base, unsigned long size)
{
    unsigned long address;

    for (address = base & SECTION_MASK; address < base + size;
         address += SECTION_SIZE) {
        pgd_t *pgd = pgd_offset_k(address);
        p4d_t *p4d = p4d_offset(pgd, address);
        pud_t *pud = pud_offset(p4d, address);
        pmd_t *pmd = pmd_offset(pud, address);
        /* ARM short-descriptor Linux PMDs contain two 1 MiB sections. */
        u32 value = pmd_val(pmd[(address >> SECTION_SHIFT) & 1]);

        if ((value & PMD_TYPE_MASK) != PMD_TYPE_SECT ||
            (value & SECTION_MASK) != address ||
            (value & (PMD_SECT_TEX(7) | PMD_SECT_CACHEABLE |
                      PMD_SECT_BUFFERABLE)))
            return false;
    }
    return true;
}

static int a6_fb_mmap(struct fb_info *info, struct vm_area_struct *vma)
{
    if (vma->vm_flags & VM_EXEC)
        return -EPERM;
    vm_flags_clear(vma, VM_MAYEXEC);
    vma->vm_page_prot = pgprot_stronglyordered(vma_get_page_prot(vma));
    /* vm_iomap_memory bounds both page offset and length to this buffer. */
    return vm_iomap_memory(vma, info->fix.smem_start, info->fix.smem_len);
}

static const struct fb_ops a6_fb_ops = {
    .owner = THIS_MODULE,
    .fb_read = fb_io_read,
    .fb_write = fb_io_write,
    .fb_mmap = a6_fb_mmap,
};

static int __init a6_fb_init(void)
{
    struct fb_info *info;
    struct platform_device *device;
    u32 base = READ_ONCE(a6_fb_base_saved);
    u32 words = READ_ONCE(a6_fb_words_saved);
    u32 stride = READ_ONCE(a6_fb_stride_saved);
    u32 width, height, size;
    int error;

    if (!of_machine_is_compatible("apple,n42ap"))
        return -ENODEV;
    /* Only the observed n42 buffer extent and its two possible orientations.
     * Geometry comes from saved live Boot_Video metadata, not a guessed DT.
     */
    if (base != 0xbf7aa000 || words != 640 * 1136 ||
        (stride != 640 * 4 && stride != 1136 * 4)) {
        pr_err("a6-fb: refusing unexpected boot video %08x/%u/%u\n",
               base, words, stride);
        return -EINVAL;
    }
    width = stride / 4;
    height = words / width;
    size = words * 4;
    if (!a6_fb_mapping_valid(base, size)) {
        pr_err("a6-fb: inherited mapping is not identity/strongly-ordered\n");
        return -EINVAL;
    }
#ifdef A6_DIRECT_DRM
    /* Geometry and inherited attributes were validated above. Register only
     * simpledrm in this profile; no second fbdev owner of the same aperture.
     */
    {
        struct resource resource = {
            .start = base, .end = base + size - 1, .flags = IORESOURCE_MEM,
        };
        struct simplefb_platform_data data = {
            .width = width, .height = height, .stride = stride,
            .format = "x8r8g8b8",
        };
        device = platform_device_register_resndata(NULL, "simple-framebuffer",
                   PLATFORM_DEVID_NONE, &resource, 1, &data, sizeof(data));
        if (IS_ERR(device))
            return PTR_ERR(device);
        pr_info("a6-drm: validated inherited framebuffer registered %ux%u\n",
                width, height);
        return 0;
    }
#endif
    if (!request_mem_region(base, size, "a6-boot-framebuffer"))
        return -EBUSY;
    /* Xorg's fbdev helper checks fb0/device/subsystem to distinguish platform
     * framebuffers from PCI devices. Supply a real parent on the platform bus.
     */
    device = platform_device_register_simple("a6-boot-framebuffer", -1, NULL, 0);
    if (IS_ERR(device)) {
        error = PTR_ERR(device);
        goto release_region;
    }
    info = framebuffer_alloc(0, &device->dev);
    if (!info) {
        error = -ENOMEM;
        goto release_device;
    }
    strscpy(info->fix.id, "a6-boot-fb", sizeof(info->fix.id));
    info->fix.smem_start = base;
    info->fix.smem_len = size;
    info->fix.type = FB_TYPE_PACKED_PIXELS;
    info->fix.visual = FB_VISUAL_TRUECOLOR;
    info->fix.line_length = stride;
    info->fix.accel = FB_ACCEL_NONE;
    info->var.xres = info->var.xres_virtual = width;
    info->var.yres = info->var.yres_virtual = height;
    info->var.bits_per_pixel = 32;
    info->var.red.offset = 16;
    info->var.red.length = info->var.green.length = info->var.blue.length = 8;
    info->var.green.offset = 8;
    info->var.width = info->var.height = -1;
    info->var.vmode = FB_VMODE_NONINTERLACED;
    info->fbops = &a6_fb_ops;
    /* This is an existing, validated virtual identity mapping. Do not
     * ioremap_wc() it: that would create aliases with conflicting attributes.
     */
    info->screen_base = (void __iomem *)(unsigned long)base;
    info->screen_size = size;
    error = register_framebuffer(info);
    if (error)
        goto release_info;
    pr_info("a6-fb: fb%d %ux%u stride=%u base=%08x size=%u strongly-ordered\n",
            info->node, width, height, stride, base, size);
    return 0;

release_info:
    framebuffer_release(info);
release_device:
    platform_device_unregister(device);
release_region:
    release_mem_region(base, size);
    return error;
}
device_initcall(a6_fb_init);
MODULE_LICENSE("GPL");

/* Native ARM userspace framebuffer proof, using the pinned Linux fb ABI.
 * Draws a labelled display test, not a window manager or interactive desktop.
 */
#include "a6-fb-uapi.h"
typedef unsigned int u32;
extern const unsigned char a6_fb_font[];
static int call(int n, u32 a, u32 b, u32 c, u32 d, u32 e, u32 f)
{
    register u32 r0 __asm__("r0")=a, r1 __asm__("r1")=b;
    register u32 r2 __asm__("r2")=c, r3 __asm__("r3")=d;
    register u32 r4 __asm__("r4")=e, r5 __asm__("r5")=f;
    register int r7 __asm__("r7")=n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1),"r"(r2),"r"(r3),
                     "r"(r4),"r"(r5),"r"(r7) : "memory","cc");
    return (int)r0;
}
#define SC(n,a,b,c,d,e,f) call(n,(u32)(a),(u32)(b),(u32)(c),(u32)(d),(u32)(e),(u32)(f))
static void say(const char *s) {u32 n=0;while(s[n])n++;SC(4,1,s,n,0,0,0);}
static void need(int ok,const char *why) {
    if(ok)return;
    say("FAIL ");say(why);say("\n");SC(1,1,0,0,0,0,0);for(;;){}
}
static int error(u32 result) {return result>=0xfffff001U;}
static volatile u32 *pixels;
static u32 width,height;
static void rect(u32 x,u32 y,u32 w,u32 h,u32 color) {
    need(x<=width && y<=height && w<=width-x && h<=height-y,"drawing bounds");
    for(u32 row=y;row<y+h;row++)
        for(u32 col=x;col<x+w;col++)pixels[row*width+col]=color;
}
static void text(u32 x,u32 y,const char *s,u32 scale,u32 color) {
    for(;*s;s++,x+=8*scale)
        for(u32 row=0;row<8;row++)
            for(u32 col=0;col<8;col++)
                if(a6_fb_font[(unsigned char)*s*8+row]&(0x80>>col))
                    rect(x+col*scale,y+row*scale,scale,scale,color);
}
int main(void) {
    struct fb_fix_screeninfo fix;
    struct fb_var_screeninfo var;
    _Static_assert(sizeof(fix)==68,"ARM fb_fix ABI");
    _Static_assert(sizeof(var)==160,"ARM fb_var ABI");
    int fd=SC(5,"/dev/fb0",2,0,0,0,0);need(fd>=0,"open fb0");
    need(SC(54,fd,0x4602,&fix,0,0,0)==0,"FBIOGET_FSCREENINFO");
    need(SC(54,fd,0x4600,&var,0,0,0)==0,"FBIOGET_VSCREENINFO");
    const char id[]="a6-boot-fb";
    for(u32 i=0;i<sizeof(id);i++)need(fix.id[i]==id[i],"driver identity");
    width=var.xres;height=var.yres;
    need((width==640 && height==1136)||(width==1136 && height==640),"geometry");
    need(fix.smem_start==0xbf7aa000 && fix.smem_len==640*1136*4 &&
         fix.line_length==width*4 && var.bits_per_pixel==32 &&
         var.xres_virtual==width && var.yres_virtual==height &&
         var.xoffset==0 && var.yoffset==0,"buffer extent");
    need(var.red.offset==16 && var.green.offset==8 && var.blue.offset==0 &&
         var.red.length==8 && var.green.length==8 && var.blue.length==8,"pixel format");
    say("PASS fbdev identity/geometry\n");
    u32 result=SC(192,0,4096,3,1,fd,fix.smem_len>>12);
    need(error(result),"mmap past buffer must fail");
    result=SC(192,0,4096,5,1,fd,0);
    need(error(result),"executable mmap must fail");
    result=SC(192,0,fix.smem_len,3,1,fd,0);
    need(!error(result),"framebuffer mmap");pixels=(volatile u32 *)result;
    u32 saved=pixels[0],probe=0x005a3c17,readback=0;
    pixels[0]=probe;__asm__ volatile("dsb sy":::"memory");
    need(SC(3,fd,&readback,4,0,0,0)==4 && readback==probe,"mmap/read coherence");
    pixels[0]=saved;
    say("PASS fbdev mmap bounds/nonexec/coherence\n");
    rect(0,0,width,height,0x00151b24);
    rect(0,0,width,12,0x001793d1);
    text(32,48,"ARCH LINUX ARM",4,0x00f0f4fa);
    text(32,112,"APPLE A6",3,0x001793d1);
    text(32,184,"NATIVE USERSPACE",3,0x00d0dae8);
    text(32,228,"FRAMEBUFFER TEST",3,0x00d0dae8);
    rect(32,300,160,100,0x00ff0000);
    rect(208,300,160,100,0x0000ff00);
    rect(384,300,160,100,0x000000ff);
    text(32,440,"RED   GREEN  BLUE",3,0x00f0f4fa);
    text(32,height-88,"USB SHELL ACTIVE",3,0x008ee0b1);
    __asm__ volatile("dsb sy":::"memory");
    need(SC(91,pixels,fix.smem_len,0,0,0,0)==0,"framebuffer munmap");
    need(SC(6,fd,0,0,0,0,0)==0,"framebuffer close");
    say("A6 FRAMEBUFFER DRAW PASS\n");return 0;
}

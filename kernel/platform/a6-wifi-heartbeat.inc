/* RAM-only native diagnostic strip; inherited validated framebuffer only. */
#include <linux/capability.h>
static const unsigned char glyph[36][5]={
 {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},{33,65,69,75,49},
 {24,20,18,127,16},{39,69,69,69,57},{60,74,73,73,48},{1,113,9,5,3},
 {54,73,73,73,54},{6,73,73,41,30},
 {126,17,17,17,126},{127,73,73,73,54},{62,65,65,65,34},{127,65,65,34,28},
 {127,73,73,73,65},{127,9,9,9,1},{62,65,73,73,122},{127,8,8,8,127},
 {0,65,127,65,0},{32,64,65,63,1},{127,8,20,34,65},{127,64,64,64,64},
 {127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},{127,9,9,9,6},
 {62,65,81,33,94},{127,9,25,41,70},{70,73,73,73,49},{1,1,127,1,1},
 {63,64,64,64,63},{31,32,64,32,31},{63,64,56,64,63},{99,20,8,20,99},
 {7,8,112,8,7},{97,81,73,69,67}};
static void text(volatile u32 *fb,u32 stride,u32 x,const char *s)
{
 for(;*s && x+10<stride;s++,x+=12){
  unsigned n=*s>='0'&&*s<='9'?*s-'0':*s>='A'&&*s<='Z'?*s-'A'+10:36;
  if(n==36)continue;
  for(unsigned a=0;a<5;a++)for(unsigned b=0;b<7;b++)if(glyph[n][a]&(1u<<b))
   for(unsigned dx=0;dx<2;dx++)for(unsigned dy=0;dy<2;dy++)
    WRITE_ONCE(fb[(b*2+5+dy)*stride+x+a*2+dx],0x00ffffff);
 }
}
static void frame(volatile u32 *fb,u32 stride,unsigned count,unsigned stage)
{
 static const char *names[]={"IDLE","FW RX","FW HASH","MODULE RX","MODULE HASH","MODULE LOAD","HSIC START","ASSOC","FIREWALL","SOAK"};
 char number[7];static const char hex[]="0123456789ABCDEF";
 for(unsigned i=0;i<6;i++)number[i]=hex[(count>>(20-i*4))&15];number[6]=0;
 for(unsigned i=0;i<stride*24;i++)WRITE_ONCE(fb[i],0);
 text(fb,stride,8,"HB");text(fb,stride,44,number);text(fb,stride,128,"STAGE");
 text(fb,stride,204,names[stage<10?stage:0]);
}

static ssize_t a6_wifi_hb_store(struct device *dev,
        struct device_attribute *attr, const char *buf, size_t count)
{
    unsigned value, stage;
    u32 base = READ_ONCE(a6_fb_base_saved);
    u32 words = READ_ONCE(a6_fb_words_saved);
    u32 stride = READ_ONCE(a6_fb_stride_saved);
    if (!capable(CAP_SYS_RAWIO))
        return -EPERM;
    if (count > 32 || sscanf(buf, "%x %x", &value, &stage) != 2 || stage > 9)
        return -EINVAL;
    if (base != 0xbf7aa000 || words != 640*1136 ||
        (stride != 640*4 && stride != 1136*4))
        return -ENODEV;
    frame((volatile u32 *)(unsigned long)base, stride/4, value, stage);
    wmb();
    return count;
}
static DEVICE_ATTR(wifi_heartbeat, 0200, NULL, a6_wifi_hb_store);

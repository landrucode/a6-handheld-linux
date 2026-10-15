/* RAM diagnostic: keep already-compressed backing files out of zram.
 * Stop this process to release locks; no file contents are changed. */
typedef unsigned int u32;
typedef unsigned long long u64;
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
static void say(const char *s) {
    u32 n=0; while(s[n]) n++;
    SC(4,1,s,n,0,0,0);
}
static void need(int ok, const char *why) {
    if(ok) return;
    say("FAIL "); say(why); say("\n"); SC(1,1,0,0,0,0,0);
    for(;;) {}
}
int main(void) {
 const char *paths[]={"/tmp/a6-desktop.squashfs","/tmp/a6-browser-images/browser.squashfs"};
 u32 unlimited[2]={0xffffffffU,0xffffffffU};
 need(SC(75,8,unlimited,0,0,0,0)==0,"memlock limit");
 for(int i=0;i<2;i++) {
  int fd=SC(5,paths[i],0,0,0,0,0); need(fd>=0,"open image");
  int size=SC(19,fd,0,2,0,0,0); need(size>0,"image size");
  int addr=SC(192,0,size,1,1,fd,0);
  need((u32)addr<0xfffff000U,"map image");
  need(SC(150,addr,size,0,0,0,0)==0,"lock image");
  SC(6,fd,0,0,0,0,0); say("IMAGE_PINNED\n");
 }
 say("COMPRESSED_IMAGES_RESIDENT\n");
 for(;;) SC(29,0,0,0,0,0,0);
}

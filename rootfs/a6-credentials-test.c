/* Reproduce Xorg Popen credential setup with ARM EABI syscalls.
 * Set IDs only to their current values; no persistent state or privilege change.
 * Syscall numbers from pinned arch/arm/tools/syscall.tbl.
 */
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
 int uid=SC(199,0,0,0,0,0,0), gid=SC(200,0,0,0,0,0,0);
 int g=SC(214,gid,0,0,0,0,0), u=SC(213,uid,0,0,0,0,0);
 if(g==-38) say("setgid32: ENOSYS\n");
 if(u==-38) say("setuid32: ENOSYS\n");
 need(g==0 && u==0,"Xorg child credential calls");
 say("PASS Xorg child credential calls\n"); return 0;
}

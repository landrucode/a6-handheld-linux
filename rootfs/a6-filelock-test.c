/* Reproduce the nonblocking exclusive flock used for a Wayland socket lock.
 * RAM-only file; ARM EABI syscall numbers from pinned Linux syscall.tbl.
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
 int fd=SC(5,"/tmp/a6-filelock-proof",66,0600,0,0,0);
 need(fd>=0,"open RAM lockfile");
 int result=SC(143,fd,2|4,0,0,0,0);
 if(result==-38)say("flock: ENOSYS\n");
 need(result==0,"Wayland socket file lock");
 need(SC(143,fd,8,0,0,0,0)==0,"unlock");
 SC(6,fd,0,0,0,0,0); SC(10,"/tmp/a6-filelock-proof",0,0,0,0,0);
 say("PASS Wayland socket file lock\n"); return 0;
}

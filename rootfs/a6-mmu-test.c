/* Bounded ARM EABI MMU semantic checks. No libc, storage, or device access.
 * Raw ABI definitions checked against the pinned Linux ARM UAPI.
 * Run under qemu-arm-static first; that validates the harness, not A6 MMU.
 */
typedef unsigned int u32;
_Static_assert(sizeof(void *) == 4, "ARM32 required");
static int call(int n, u32 a, u32 b, u32 c, u32 d, u32 e, u32 f)
{
    register u32 r0 __asm__("r0") = a, r1 __asm__("r1") = b;
    register u32 r2 __asm__("r2") = c, r3 __asm__("r3") = d;
    register u32 r4 __asm__("r4") = e, r5 __asm__("r5") = f;
    register int r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3),
                     "r"(r4), "r"(r5), "r"(r7) : "memory", "cc");
    return (int)r0;
}
#define SC(n,a,b,c,d,e,f) call(n,(u32)(a),(u32)(b),(u32)(c),(u32)(d),(u32)(e),(u32)(f))
__attribute__((noreturn)) static void done(int status)
{
    SC(1,status,0,0,0,0,0);
    for (;;) {}
}
static void need(int condition, int code) { if (!condition) done(code); }
static void say(const char *s)
{
    u32 n = 0; while (s[n]) n++;
    while (n) {
        int r = SC(4,1,s,n,0,0,0);
        if (r == -4) continue;
        need(r > 0, 90); s += r; n -= r;
    }
}
static volatile u32 *mapping(void)
{
    int r = SC(192,0,12288,3,0x22,-1,0); /* private anonymous RW */
    need((u32)r < 0xfffff001U, 10);
    volatile u32 *p = (volatile u32 *)(u32)r;
    for (u32 i=0; i<3072; i++) p[i] = 0x12340000U+i;
    for (u32 i=0; i<3072; i++) need(p[i] == 0x12340000U+i,11);
    return p;
}
static volatile u32 *expected_address;
static int expected_code;
static void fault(int sig, int *info, void *context)
{
    (void)context;
    done(sig == 11 && info[0] == 11 && info[2] == expected_code &&
         (u32)info[3] == (u32)expected_address ? 0 : 12);
}
static void expect_fault(volatile u32 *p, int code)
{
    /* Kernel rt_sigaction layout, not legacy libc struct sigaction. */
    struct { void (*handler)(int,int *,void *); u32 flags,restorer,mask[2]; }
        action = {fault,4,0,{0,0}}; /* SA_SIGINFO; handler never returns */
    expected_address=p; expected_code=code;
    need(SC(174,11,&action,0,8,0,0) == 0,13);
}
static void protection(void)
{
    volatile u32 *p=mapping(), *middle=p+1024;
    expect_fault(middle,2); /* SEGV_ACCERR */
    need(SC(125,middle,4096,1,0,0,0) == 0,20);
    need(*middle == 0x12340400U,21);
#ifndef A6_TEST_INJECT_SKIP_FAULT
    *middle=0xdeadbeef; /* must fault after previously cached writable access */
#endif
    done(22);
}
static void unmap_fault(void)
{
    volatile u32 *p=mapping(), *middle=p+1024;
    expect_fault(middle,1); /* SEGV_MAPERR */
    need(SC(91,middle,4096,0,0,0,0) == 0,30);
    (void)*middle;
    done(31);
}
static void remap(void)
{
    volatile u32 *p=mapping(), *middle=p+1024;
    need(SC(125,middle,4096,1,0,0,0) == 0,40);
    need(SC(125,middle,4096,3,0,0,0) == 0,41);
    *middle=0xabcdef01; need(*middle == 0xabcdef01,42);
    need(SC(91,middle,4096,0,0,0,0) == 0,43);
    need((u32)SC(192,middle,4096,3,0x32,-1,0) == (u32)middle,44);
    for (u32 i=0;i<1024;i++) { need(middle[i] == 0,45); middle[i]=0xfeed0000+i; }
    for (u32 i=0;i<1024;i++) {
        need(p[i] == 0x12340000+i && p[2048+i] == 0x12340800+i,46);
        need(middle[i] == 0xfeed0000+i,47);
    }
    need(SC(91,p,12288,0,0,0,0) == 0,48);
}
static void closefd(int fd) { need(SC(6,fd,0,0,0,0,0)==0,50); }
static void byte(int nr,int fd)
{
    char value='x'; int r;
    do { r=SC(nr,fd,&value,1,0,0,0); } while (r==-4);
    need(r==1 && value=='x',51);
}
static int waited(int pid)
{
    int status=-1,r;
    do { r=SC(114,pid,&status,0,0,0,0); } while (r==-4);
    need(r==pid,52); return status;
}
static void cow(void)
{
    volatile u32 *p=mapping(); int to_child[2],to_parent[2];
    need(SC(42,to_child,0,0,0,0,0)==0,53);
    need(SC(42,to_parent,0,0,0,0,0)==0,54);
    int pid=SC(2,0,0,0,0,0,0); need(pid>=0,55);
    if (!pid) {
        closefd(to_child[1]); closefd(to_parent[0]);
        byte(3,to_child[0]); /* parent writes first, child must see original */
        for(u32 i=0;i<3072;i++) need(p[i]==0x12340000+i,56);
        for(u32 i=0;i<3072;i++) p[i]=0xc11d0000+i;
        byte(4,to_parent[1]); byte(3,to_child[0]);
        for(u32 i=0;i<3072;i++) need(p[i]==0xc11d0000+i,57);
        done(0);
    }
    closefd(to_child[0]); closefd(to_parent[1]);
    for(u32 i=0;i<3072;i++) p[i]=0xface0000+i;
    byte(4,to_child[1]); byte(3,to_parent[0]);
    for(u32 i=0;i<3072;i++) need(p[i]==0xface0000+i,58);
    for(u32 i=0;i<3072;i++) p[i]=0xbeef0000+i;
    byte(4,to_child[1]); need(waited(pid)==0,59);
    for(u32 i=0;i<3072;i++) need(p[i]==0xbeef0000+i,60);
    closefd(to_child[1]); closefd(to_parent[0]);
    need(SC(91,p,12288,0,0,0,0)==0,61);
}
static int run_tests(void)
{
    void (*tests[])(void)={protection,unmap_fault,remap,cow};
    const char *names[]={"mprotect ACCERR", "munmap MAPERR", "remap zero/guards", "fork COW isolation"};
    for(u32 i=0;i<4;i++) {
        say("BEGIN "); say(names[i]); say("\n");
        int pid=SC(2,0,0,0,0,0,0); need(pid>=0,70);
        if(!pid) { tests[i](); done(0); }
        int status=waited(pid);
        if(status) {
            char hex[9]; const char *digits="0123456789abcdef";
            for(int j=0;j<8;j++) hex[j]=digits[((u32)status>>(28-4*j))&15];
            hex[8]=0; say("FAIL wait-status 0x"); say(hex); say("\n"); done(1);
        }
        say("PASS "); say(names[i]); say("\n");
    }
    say("A6-MMU PASS 4\n"); return 0;
}

int main(void)
{
    /* This kernel disables POSIX interval timers. Supervise a private process
     * group with wait4(WNOHANG) and nanosleep instead. Includes COW descendants.
     */
    int pid=SC(2,0,0,0,0,0,0); need(pid>=0,80);
    if(!pid) { need(SC(57,0,0,0,0,0,0)==0,81); done(run_tests()); }
    need(SC(57,pid,pid,0,0,0,0)==0,82);
    for(int i=0;i<100;i++) {
        int status=-1, r=SC(114,pid,&status,1,0,0,0);
        if(r==pid) {
            SC(37,-pid,9,0,0,0,0); /* clean up any surviving test descendants */
            if(status) { say("FAIL supervised worker\n"); return 1; }
            return 0;
        }
        need(r==0 || r==-4,83);
        u32 pause[2]={0,100000000};
        need(SC(162,pause,0,0,0,0,0)==0,84);
    }
    SC(37,-pid,9,0,0,0,0);
    (void)waited(pid);
    say("FAIL watchdog timeout\n"); return 1;
}

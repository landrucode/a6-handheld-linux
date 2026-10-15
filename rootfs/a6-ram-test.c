/* Bounded anonymous RAM test; no physical memory or storage access. */
#ifndef A6_RAM_TEST_MIB
#define A6_RAM_TEST_MIB 256
#endif
#if A6_RAM_TEST_MIB == 256
#define A6_RAM_FREE_MIB 320
#elif A6_RAM_TEST_MIB == 640
#define A6_RAM_FREE_MIB 704
#else
#error unsupported RAM test size
#endif
#define TEXT_INNER(x) #x
#define TEXT(x) TEXT_INNER(x)
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

struct info {
    int uptime; u32 loads[3], totalram, freeram, sharedram, bufferram;
    u32 totalswap, freeswap; unsigned short procs, pad;
    u32 totalhigh, freehigh, unit; char padding[8];
};
_Static_assert(sizeof(struct info)==64,"ARM sysinfo ABI");
int main(void) {
    struct info info;
    need(SC(116,&info,0,0,0,0,0)==0,"sysinfo");
    need((u64)info.freeram*info.unit >= (u64)A6_RAM_FREE_MIB*1024*1024,
         "requires " TEXT(A6_RAM_FREE_MIB) " MiB free RAM; refusing allocation");
    const u32 bytes=A6_RAM_TEST_MIB*1024U*1024, words=bytes/4;
    u32 address=(u32)SC(192,0,bytes,3,0x22,-1,0);
    need(address<0xfffff001U,"anonymous mmap" TEXT(A6_RAM_TEST_MIB) " MiB");
    volatile u32 *p=(volatile u32 *)address;
    for(u32 pass=0;pass<2;++pass) {
        u32 salt=pass ? 0xa5a5a5a5U : 0x5a5a5a5aU;
        for(u32 i=0;i<words;++i)p[i]=(i*0x9e3779b1U)^salt;
        for(u32 i=0;i<words;++i)
            need(p[i]==((i*0x9e3779b1U)^salt),"RAM pattern mismatch");
        say("PASS " TEXT(A6_RAM_TEST_MIB) " MiB complete write/read pattern\n");
    }
    need(SC(91,address,bytes,0,0,0,0)==0,"munmap");
    say("A6 RAM" TEXT(A6_RAM_TEST_MIB) " PASS; allocation released\n");
    return 0;
}

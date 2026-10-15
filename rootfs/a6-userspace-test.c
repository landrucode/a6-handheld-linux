/* ARM EABI userspace services exercised without libc. All waits are bounded;
 * sockets/descriptors are nonblocking. ABI values from pinned Linux UAPI.
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
static void closefd(int fd) { need(SC(6,fd,0,0,0,0,0)==0,"close"); }
struct event { u32 events; u64 data; };
_Static_assert(sizeof(struct event)==16,"ARM epoll ABI");
static int sockets(void) {
    int fds[2]; char sent='A',received=0;
    if(SC(288,1,1|0x800,0,fds,0,0)<0) {say("MISSING unix socketpair\n");return 1;}
    need(SC(4,fds[0],&sent,1,0,0,0)==1,"socket write");
    need(SC(3,fds[1],&received,1,0,0,0)==1 && received==sent,"socket read");
    closefd(fds[0]);closefd(fds[1]);say("PASS unix socketpair\n");return 0;
}
static int events(void) {
    int ep=SC(357,0,0,0,0,0,0),fd=SC(356,0,0x800,0,0,0,0);
    if(ep<0 || fd<0) {
        if(ep>=0)closefd(ep);if(fd>=0)closefd(fd);
        say("MISSING epoll/eventfd\n");return 1;
    }
    struct event add={1,42},got={0,0};u64 count=7,readback=0;
    need(SC(251,ep,1,fd,&add,0,0)==0,"epoll add");
    need(SC(4,fd,&count,8,0,0,0)==8,"eventfd write");
    need(SC(252,ep,&got,1,1000,0,0)==1 && got.data==42 && (got.events&1),"epoll ready");
    need(SC(3,fd,&readback,8,0,0,0)==8 && readback==count,"eventfd count");
    need(SC(252,ep,&got,1,0,0,0)==0,"epoll drained");
    closefd(fd);closefd(ep);say("PASS epoll/eventfd\n");return 0;
}
static int timers(void) {
    int fd=SC(350,1,0x800,0,0,0,0);
    if(fd<0) {say("MISSING timerfd\n");return 1;}
    int ep=SC(357,0,0,0,0,0,0);need(ep>=0,"timer epoll");
    struct event add={1,43},got={0,0};
    int timer[4]={0,0,0,10000000};u64 count=0;
    need(SC(251,ep,1,fd,&add,0,0)==0,"timer epoll add");
    need(SC(353,fd,0,timer,0,0,0)==0,"timer arm");
    need(SC(252,ep,&got,1,1000,0,0)==1 && got.data==43,"timer expiration");
    need(SC(3,fd,&count,8,0,0,0)==8 && count==1,"timer read");
    closefd(fd);closefd(ep);say("PASS timerfd expiration\n");return 0;
}
static int signals(void) {
    u32 mask[2]={1U<<9,0},old[2]={0,0},info[32];
    need(SC(175,0,mask,old,8,0,0)==0,"block SIGUSR1");
    int fd=SC(355,-1,mask,8,0x800,0,0);
    if(fd<0) {
        need(SC(175,2,old,0,8,0,0)==0,"restore signals");
        say("MISSING signalfd\n");return 1;
    }
    int pid=SC(20,0,0,0,0,0,0);
    need(SC(37,pid,10,0,0,0,0)==0,"send SIGUSR1");
    need(SC(3,fd,info,128,0,0,0)==128 && info[0]==10 && info[3]==(u32)pid,"signalfd record");
    closefd(fd);need(SC(175,2,old,0,8,0,0)==0,"restore signals");
    say("PASS signalfd\n");return 0;
}
static int notifications(void) {
    int fd=SC(360,0x800,0,0,0,0,0);
    if(fd<0){say("MISSING inotify\n");return 1;}
    int watch=SC(317,fd,"/tmp",0x20,0,0,0); /* IN_OPEN */
    need(watch>=0,"inotify watch");
    int directory=SC(5,"/tmp",0,0,0,0,0);need(directory>=0,"open watched directory");
    u32 event[4];
    need(SC(3,fd,event,sizeof(event),0,0,0)==16 &&
         event[0]==(u32)watch && (event[1]&0x20),"inotify open event");
    closefd(directory);closefd(fd);say("PASS inotify event\n");return 0;
}
static int posix_timer(void) {
    int id=-1;
    if(SC(257,1,0,&id,0,0,0)<0){say("MISSING POSIX timers\n");return 1;}
    need(SC(261,id,0,0,0,0,0)==0,"timer delete");
    say("PASS POSIX timer lifecycle\n");return 0;
}
int main(void) {
    int failures=sockets();failures+=events();failures+=timers();
    failures+=signals();failures+=notifications();failures+=posix_timer();
    if(failures){say("A6 USERSPACE MISSING FEATURES\n");return 1;}
    say("A6 USERSPACE PASS 6\n");return 0;
}

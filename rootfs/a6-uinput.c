/* Temporary synthetic input for direct Weston; fixed root-owned RAM FIFO. */
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


void *memset(void *dest, int value, unsigned int size) {
    volatile unsigned char *p=dest;
    for(unsigned int i=0;i<size;++i)p[i]=(unsigned char)value;
    return dest;
}
struct setup { unsigned short bus,vendor,product,version; char name[80]; u32 ff; };
struct event { u32 sec,usec; unsigned short type,code; int value; };
_Static_assert(sizeof(struct setup)==92,"ARM uinput setup ABI");
_Static_assert(sizeof(struct event)==16,"ARM input_event ABI");
static void ioctl_ok(int fd,u32 request,u32 arg) { need(SC(54,fd,request,arg,0,0,0)==0,"uinput ioctl"); }
static int create(int mouse) {
    int fd=SC(5,"/dev/uinput",1,0,0,0,0);
    need(fd>=0,"open uinput");
    ioctl_ok(fd,0x40045564,1);
    if(mouse) {
        ioctl_ok(fd,0x40045564,2);
        ioctl_ok(fd,0x40045566,0);ioctl_ok(fd,0x40045566,1);ioctl_ok(fd,0x40045566,8);
        for(u32 code=0x110;code<=0x112;++code)ioctl_ok(fd,0x40045565,code);
    } else for(u32 code=1;code<128;++code)ioctl_ok(fd,0x40045565,code);
    struct setup data={.bus=6,.vendor=0x106,.product=mouse?2:1,.version=1};
    const char *name=mouse?"A6 USB synthetic pointer":"A6 USB synthetic keyboard";
    for(u32 i=0;name[i];++i)data.name[i]=name[i];
    ioctl_ok(fd,0x405c5503,(u32)&data);ioctl_ok(fd,0x5501,0);
    return fd;
}
int main(void) {
    int keyboard=create(0),pointer=create(1);
    int pipe=SC(5,"/tmp/a6-input-events",2,0,0,0,0);
    need(pipe>=0,"open root-owned input FIFO");
    say("A6_UINPUT_READY\n");
    for(;;) {
        u32 command[4],done=0;
        while(done<sizeof(command)) {
            int n=SC(3,pipe,(char *)command+done,sizeof(command)-done,0,0,0);
            if(n==-4)continue;
            need(n>0,"read input command");done+=(u32)n;
        }
        u32 device=command[0],type=command[1],code=command[2];int value=(int)command[3];
        int valid=device==0 && type==1 && code>0 && code<128 && (value==0||value==1);
        valid|=device==1 && type==1 && code>=0x110 && code<=0x112 && (value==0||value==1);
        valid|=device==1 && type==2 && (code==0||code==1||code==8) && value>=-2048 && value<=2048;
        if(!valid) {say("REJECT input command\n");continue;}
        struct event events[2]={{.type=type,.code=code,.value=value},{0}};
        need(SC(4,device?pointer:keyboard,events,sizeof(events),0,0,0)==sizeof(events),"write input events");
    }
}

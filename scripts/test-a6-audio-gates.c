// SPDX-License-Identifier: GPL-2.0-only
/* Host MMIO fault injection of the actual audio sysfs handler. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <stdarg.h>
#include <sys/types.h>
typedef uint32_t u32;
#define __iomem
#define __init
#define U32_MAX UINT32_MAX
#define CAP_SYS_RAWIO 1
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define A6_TOUCH_I2C_GATE 0x118
static uint8_t pmgr[4096], gpio[4096], i2c[4096], mca[4096];
static void *a6_touch_pmgr=pmgr,*a6_touch_gpio=gpio,*a6_touch_i2c=i2c;
static int a6_touch_lock, lock_busy, fail_enable=-1, fail_restore=-1, writes, reads_mca;
static void *firmware_kobj;
struct kobject {};
struct attribute {int dummy;};
struct kobj_attribute {struct attribute attr;};
struct attribute_group {const char *name;struct attribute **attrs;};
#define __ATTR(...) {{0}}
#define late_initcall(x)
static int capable(int x){return 1;}
static int mutex_trylock(int *p){return !lock_busy;}
static void mutex_lock(int *p){}
static void mutex_unlock(int *p){}
static void usleep_range(int a,int b){}
static int sysfs_streq(const char *a,const char *b){return !strcmp(a,b);}
static u32 readl(void *p){u32 v;memcpy(&v,p,4);if((uint8_t *)p>=mca&&(uint8_t *)p<mca+4096)reads_mca++;return v;}
static void writel(u32 v,void *p){
 assert((uint8_t *)p==pmgr+0xa0||(uint8_t *)p==pmgr+0xe0);
 int index=((uint8_t *)p==pmgr+0xa0)?0:1;writes++;
 if((v&15)==15){if(index==fail_enable)v=(v&~255U)|15;else v=(v&~255U)|255;}
 else if(index==fail_restore)v=(v&~255U)|255;
 memcpy(p,&v,4);
}
#define readl_poll_timeout(p,v,cond,interval,timeout) ({int r=-ETIMEDOUT;for(int q=0;q<10;q++){v=readl(p);if(cond){r=0;break;}}r;})
static int sysfs_emit(char *b,const char *f,...){va_list a;va_start(a,f);int n=vsprintf(b,f,a);va_end(a);return n;}
#define sysfs_emit_at(b,n,...) sysfs_emit((b)+(n),__VA_ARGS__)
static int of_machine_is_compatible(const char *s){return 1;}
static void *ioremap(unsigned long a,int n){return mca;}
static void iounmap(void *p){}
static int sysfs_create_group(void *p,const void *q){return 0;}
#include "../kernel/platform/a6-audio-gate-observe.inc"
static void setup(void){memset(pmgr,0,sizeof(pmgr));memset(mca,0,sizeof(mca));a6_audio_mca=mca;a6_audio_attempted=false;a6_audio_sampled=false;a6_audio_result=a6_audio_cleanup=0;writes=reads_mca=lock_busy=0;fail_enable=fail_restore=-1;}
static int run(void){return a6_audio_run_store(0,0,"snapshot-enable-restore",23);}
int main(void){
 setup();assert(run()==23);assert(writes==4&&reads_mca==4);assert(readl(pmgr+0xa0)==0&&readl(pmgr+0xe0)==0);assert(run()==-EALREADY&&writes==4);
 for(int f=0;f<2;f++){setup();fail_enable=f;assert(run()==-ETIMEDOUT);assert(!reads_mca);assert(readl(pmgr+0xa0)==0&&readl(pmgr+0xe0)==0);}
 for(int f=0;f<2;f++){setup();fail_restore=f;assert(run()==-EUCLEAN);assert(a6_audio_cleanup==-EUCLEAN);assert(readl(pmgr+(f==0?0xe0:0xa0))==0);}
 setup();u32 on=0x2ff;memcpy(pmgr+0xa0,&on,4);assert(run()==23);assert(writes==2&&readl(pmgr+0xa0)==on);
 setup();u32 bad=U32_MAX;memcpy(pmgr+0xe0,&bad,4);assert(run()==-EBUSY&&writes==0&&reads_mca==0);
 setup();lock_busy=1;assert(run()==-EBUSY&&writes==0&&!a6_audio_attempted);
 puts("PASS: actual kernel handler success, partial enable timeouts, both restore failures, inherited parent, invalid gate, one-shot and bounded lock");
}

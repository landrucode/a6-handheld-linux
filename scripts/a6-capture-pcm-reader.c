/* Headless ARM EABI ALSA capture probe: no libc, WAV, or audio server.
 * Build against the candidate kernel UAPI, not hand-copied ioctl layouts. */
#define __KERNEL__ 1
struct timespec { long tv_sec, tv_nsec; };
#include <asm/ioctl.h>
#include <sound/asound.h>
#ifdef __arm__
_Static_assert(sizeof(struct snd_pcm_hw_params)==604,"ARM32 HW_PARAMS ABI");
_Static_assert(sizeof(struct snd_pcm_sw_params)==104,"ARM32 SW_PARAMS ABI");
_Static_assert(sizeof(struct snd_xferi)==12,"ARM32 READI ABI");
#endif
static long call3(long nr,long a,long b,long c)
{
 register long r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r7 __asm__("r7")=nr;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory","cc");return r0;
}
void *memset(void *p,int v,unsigned n){unsigned char *q=p;while(n--)*q++=v;return p;}
static void text(const char *s){unsigned n=0;while(s[n])n++;call3(4,1,(long)s,n);}
static void number(unsigned n){char b[16];unsigned i=sizeof(b);do{b[--i]='0'+n%10;n/=10;}while(n);call3(4,1,(long)(b+i),sizeof(b)-i);}
static void value(const char *s,unsigned n){text(s);number(n);text("\n");}
static void exact(struct snd_pcm_hw_params *p,unsigned k,unsigned v){struct snd_interval *i=&p->intervals[k-SNDRV_PCM_HW_PARAM_FIRST_INTERVAL];i->min=i->max=v;i->integer=1;}
static void mask(struct snd_pcm_hw_params *p,unsigned k,unsigned v){memset(&p->masks[k],0,sizeof(p->masks[k]));p->masks[k].bits[v/32]=1U<<(v%32);}
static struct snd_pcm_hw_params hw;
static struct snd_pcm_sw_params sw;
static short samples[256];
static long control(long fd,unsigned request,void *arg){return call3(54,fd,request,(long)arg);}
static int probe(void)
{
 long fd=call3(5,(long)"/dev/snd/pcmC0D0c",2,0),rc=0;unsigned stage=0,frames=0,nonzero[2]={0},peak[2]={0};struct timespec start={0},end={0};
 if(fd<0){value("open_error=",(unsigned)-fd);return 1;}
 for(unsigned k=0;k<3;k++)for(unsigned j=0;j<8;j++)hw.masks[k].bits[j]=~0U;
 for(unsigned k=0;k<12;k++)hw.intervals[k].max=~0U;
 hw.rmask=~0U;
 mask(&hw,SNDRV_PCM_HW_PARAM_ACCESS,SNDRV_PCM_ACCESS_RW_INTERLEAVED);
 mask(&hw,SNDRV_PCM_HW_PARAM_FORMAT,SNDRV_PCM_FORMAT_S16_LE);
 mask(&hw,SNDRV_PCM_HW_PARAM_SUBFORMAT,SNDRV_PCM_SUBFORMAT_STD);
 exact(&hw,SNDRV_PCM_HW_PARAM_CHANNELS,2);exact(&hw,SNDRV_PCM_HW_PARAM_RATE,44100);
 exact(&hw,SNDRV_PCM_HW_PARAM_PERIOD_SIZE,128);exact(&hw,SNDRV_PCM_HW_PARAM_BUFFER_SIZE,4096);
 stage=1;if((rc=control(fd,SNDRV_PCM_IOCTL_HW_PARAMS,&hw))<0)goto done;
 sw.period_step=1;sw.avail_min=128;sw.xfer_align=1;sw.start_threshold=4096;sw.stop_threshold=4096;
 sw.boundary=4096;while(sw.boundary<=0x3fffffffU-4096)sw.boundary*=2;
 stage=2;if((rc=control(fd,SNDRV_PCM_IOCTL_SW_PARAMS,&sw))<0)goto done;
 stage=3;if((rc=control(fd,SNDRV_PCM_IOCTL_PREPARE,0))<0)goto done;
 stage=4;if((rc=control(fd,SNDRV_PCM_IOCTL_START,0))<0)goto done;
 call3(263,1,(long)&start,0);
 stage=5;while(frames<44100){struct snd_xferi x={.buf=samples,.frames=128};
  if(x.frames>44100-frames)x.frames=44100-frames;
  rc=control(fd,SNDRV_PCM_IOCTL_READI_FRAMES,&x);if(rc<0)goto done;
  if(x.result<=0 || x.result>(long)x.frames){rc=-5;goto done;}
  for(unsigned i=0;i<(unsigned)x.result*2;i++){int v=samples[i];unsigned a=v<0 ? -v : v,c=i&1;nonzero[c]+=v!=0;if(a>peak[c])peak[c]=a;}
  if(!frames){text("first_s16_bits=");for(unsigned i=0;i<32;i++){number((unsigned short)samples[i]);text(i==31 ? "\n" : ",");}}
  frames+=x.result;
 }
 done:
 call3(263,1,(long)&end,0);
 /* DROP followed by close invokes the driver's bounded exact restoration. */
 long drop=control(fd,SNDRV_PCM_IOCTL_DROP,0),closed=call3(6,fd,0,0);
 value("stage=",stage);value("error=",rc<0 ? -rc : 0);value("frames=",frames);
 value("left_nonzero=",nonzero[0]);value("right_nonzero=",nonzero[1]);value("left_peak=",peak[0]);value("right_peak=",peak[1]);
 if(start.tv_sec){long sec=end.tv_sec-start.tv_sec,ns=end.tv_nsec-start.tv_nsec;if(ns<0){sec--;ns+=1000000000;}value("elapsed_ms=",sec*1000+ns/1000000);}
 value("drop_error=",drop<0 ? -drop : 0);value("close_error=",closed<0 ? -closed : 0);
 return rc<0 || closed<0;
}
void _start(void){int result=probe();call3(1,result,0,0);for(;;);}

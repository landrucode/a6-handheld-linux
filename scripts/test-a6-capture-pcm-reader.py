#!/usr/bin/env python3
"""Run the actual direct reader with modeled ALSA ioctls and short reads."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'scripts/a6-capture-pcm-reader.c').read_text()
a=s.index('static long call3(');b=s.index('void *memset(',a)
s=s[:a]+r'''
#include <assert.h>
static unsigned calls,closed,dropped,mode,read_frames;
static long call3(long nr,long a,long b,long c){
 if(nr==5)return 7;
 if(nr==4)return c;
 if(nr==6){closed++;return 0;}
 if(nr==263){struct timespec *t=(void *)b;t->tv_sec=10+(read_frames==44100);t->tv_nsec=0;return 0;}
 assert(nr==54 && a==7);
 switch((unsigned)b){
 case SNDRV_PCM_IOCTL_HW_PARAMS:{struct snd_pcm_hw_params *p=(void *)c;
  assert(p->masks[0].bits[0]==(1U<<SNDRV_PCM_ACCESS_RW_INTERLEAVED));
  assert(p->masks[1].bits[0]==(1U<<SNDRV_PCM_FORMAT_S16_LE));
  assert(p->intervals[SNDRV_PCM_HW_PARAM_RATE-8].min==44100);
  assert(p->intervals[SNDRV_PCM_HW_PARAM_CHANNELS-8].min==2);return 0;}
 case SNDRV_PCM_IOCTL_SW_PARAMS:{struct snd_pcm_sw_params *p=(void *)c;assert(p->avail_min==128 && p->boundary>4096);return 0;}
 case SNDRV_PCM_IOCTL_PREPARE:return mode==1 ? -5 : 0;
 case SNDRV_PCM_IOCTL_START:return 0;
 case SNDRV_PCM_IOCTL_DROP:dropped++;return 0;
 case SNDRV_PCM_IOCTL_READI_FRAMES:{struct snd_xferi *x=(void *)c;
  if(mode==2)return -32;
  assert(x->frames<=128);unsigned n=x->frames>65 ? 65 : x->frames;
  short *p=x->buf;for(unsigned i=0;i<n;i++){p[2*i]=-3;p[2*i+1]=0;}
  x->result=n;read_frames+=n;calls++;return 0;}
 default:assert(0);return -5;
 }
}
'''+s[b:]
s=s[:s.index('void _start(')]+r'''
int main(void){assert(probe()==0);assert(read_frames==44100 && calls>344 && closed==1 && dropped==1);
 mode=1;assert(probe()==1 && closed==2 && dropped==2);
 mode=2;assert(probe()==1 && closed==3 && dropped==3);return 0;}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'probe.c';p.write_text(s);exe=Path(d)/'probe'
 subprocess.run(['cc','-O1','-fno-builtin','-fsanitize=address,undefined','-I',str(root/'build/audio-reader-headers'),'-I',str(root/'build/audio-uapi/include'),str(p),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
print('PASS: reader ioctl parameters, partial stereo reads, bounded frames, prepare/read failures and close cleanup')

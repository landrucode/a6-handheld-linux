/* RAM-only heartbeat via the bounded native screen strip; no USB or libc. */
typedef unsigned int u32;
static long call6(long n,long a,long b,long c,long d,long e,long f)
{
 register long r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c;
 register long r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=n;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory","cc");
 return r0;
}
void _start(void)
{
 static const char hex[]="0123456789ABCDEF";
 long fd=call6(5,(long)"/tmp/a6-wifi-heartbeat-screen",1,0,0,0,0);
 if(fd<0)goto fail;
 for(unsigned n=0;n<43200;n++){
  char output[9],stage='0';long f=call6(5,(long)"/tmp/a6-wifi-stage",0,0,0,0,0);
  if(f>=0){call6(3,f,(long)&stage,1,0,0,0);call6(6,f,0,0,0,0,0);}
  if(stage<'0'||stage>'9')stage='0';
  for(unsigned i=0;i<6;i++)output[i]=hex[(n>>(20-i*4))&15];
  output[6]=' ';output[7]=stage;output[8]='\n';
  if(call6(4,fd,(long)output,9,0,0,0)!=9)goto fail;
  long delay[2]={1,0};call6(162,(long)delay,0,0,0,0,0);
 }
 call6(1,0,0,0,0,0,0);
fail:
 call6(1,2,0,0,0,0,0);
 for(;;){}
}

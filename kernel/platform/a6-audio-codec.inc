// SPDX-License-Identifier: GPL-2.0-only
/* CS42L65 control probe. SPI3 is separate from touch's SPI1.
 * Stock EmbeddedAudio 80a3973c frames reads 6d,page,reg&7f,00;
 * clocks five bytes under one external CS assertion and returns byte4.
 * No codec reset, PMU supply, DMA or AE2 firmware operation. */
static void __iomem *a6_ac_spi, *a6_ac_iis;
static int a6_ac_result=-EAGAIN;
static u32 a6_ac_gate[3][3], a6_ac_cs[3], a6_ac_iis_regs[3][3];
static u32 a6_ac_switch[3], a6_ac_acs[3], a6_ac_spi_before[7], a6_ac_spi_after[7];
static u8 a6_ac_reply[3][5];
static unsigned int a6_ac_reads, a6_ac_control_reads;
/* Read-only controls that stock itself reads or read-modify-writes. */
static const u32 a6_ac_control_regs[]={6,7,0x0e,0x0f,0x10,0x12,0x13,0x2e,0x218,0x242,0x243,0x24f,0xc804};
static u8 a6_ac_controls[13];
static const u32 a6_ac_spi_offsets[]={0,4,12,0x30,0x34,0x38,0x4c};
static const u32 a6_ac_gate_offsets[]={0xa0,0xa4,0xf0};
static int a6_ac_transfer(u32 reg,u8 *reply,bool writing,u8 value)
{
 unsigned int received=0,poll,i;u32 status;int ret=-ETIMEDOUT;
 /* Same DT format08010000 and SPI version1 as the proven touch PIO
  * transfer. Use the proven slow divider1024 for this short control read. */
 writel(0,a6_ac_spi);writel(1024,a6_ac_spi+0x30);writel(0,a6_ac_spi+0x38);
 writel(0x40000f,a6_ac_spi+8);writel(0x4018,a6_ac_spi+4);
 writel(writing ? 0 : 5,a6_ac_spi+0x34);writel(5,a6_ac_spi+0x4c);
 writel(0xd,a6_ac_spi);
 /* CS descriptor GPIO87 config10001: assertion is low. */
 writel(0x202,a6_touch_gpio+87*4);
 if(readl(a6_touch_gpio+87*4)!=0x202){ret=-EIO;goto stop;}
 writel(a6_ac_spi_before[2]&~2,a6_ac_spi+12);writel(0x4038,a6_ac_spi+4);
 for(i=0;i<5;i++)writel(i==0 ? (writing ? 0x6c : 0x6d) : i==1 ? reg>>8 : i==2 ? reg&0x7f : i==4 && writing ? value : 0,a6_ac_spi+0x10);
 for(poll=0;poll<1000;poll++) {
  status=readl(a6_ac_spi+8);
  if(status==U32_MAX || ((status>>6)&31)>16 || ((status>>11)&31)>(writing ? 0 : 5-received)){ret=-EIO;break;}
  while(((status>>11)&31) && received<5) {
   reply[received++]=readl(a6_ac_spi+0x20);status=readl(a6_ac_spi+8);
  }
  if((writing || received==5) && !((readl(a6_ac_spi+8)>>6)&31) && !readl(a6_ac_spi+0x34) && !readl(a6_ac_spi+0x4c)){ret=0;break;}
  if(a6_at_codec && a6_at_feeding){ret=a6_ac_feed();if(ret)break;ret=-ETIMEDOUT;}
  udelay(10);
 }
stop:
 writel(0,a6_ac_spi);writel(0x203,a6_touch_gpio+87*4);
 if(readl(a6_touch_gpio+87*4)!=0x203)a6_ac_cleanup=-EUCLEAN;
 writel(0x40000f,a6_ac_spi+8);
 return ret;
}
static int a6_ac_read_reg(u32 reg,u8 *reply){return a6_ac_transfer(reg,reply,false,0);}
#include "a6-audio-codec-play.inc"
static int a6_ac_execute_locked(bool playback)
{
 bool gates[3]={false,false,false},clocked=false,spi_changed=false;
 unsigned int i,j;u32 value;int ret;
 if(a6_ac_cleanup || a6_af_cleanup)return -EUCLEAN;
 a6_ac_reads=a6_ac_control_reads=0;memset(a6_ac_controls,0,sizeof(a6_ac_controls));memset(a6_ac_reply,0,sizeof(a6_ac_reply));
 memset(a6_ac_gate,0,sizeof(a6_ac_gate));a6_ac_cleanup=0;
 if(!a6_auto_enabled || a6_auto_fault || a6_auto_paused || !a6_low_enabled || a6_low_triggered ||
    a6_policy_vbat_mv<3600 || a6_policy_tbat_c<10 || a6_policy_tbat_c>35){ret=-EBUSY;goto out;}
 if(a6_memory_capture_copy[483]!=24000000){ret=-ENODATA;goto out;}
 /* Policy/low-battery guards above remain armed. This control-only stage
  * does not borrow the tone ADC helper: its failure path resets the amp. */
 for(i=0;i<3;i++) {
  value=readl(a6_touch_pmgr+a6_ac_gate_offsets[i]);a6_ac_gate[i][0]=value;
  if(value==U32_MAX || value!=readl(a6_touch_pmgr+a6_ac_gate_offsets[i]) ||
     ((value&255)!=0 && (value&255)!=255)){ret=-EBUSY;goto restore;}
 }
 for(i=0;i<3;i++) {
  if(!(a6_ac_gate[i][0]&255)) {
   gates[i]=true;writel(a6_ac_gate[i][0]|15,a6_touch_pmgr+a6_ac_gate_offsets[i]);
   ret=a6_af_poll(a6_touch_pmgr+a6_ac_gate_offsets[i],255,255);if(ret)goto restore;
  }
  a6_ac_gate[i][1]=readl(a6_touch_pmgr+a6_ac_gate_offsets[i]);
 }
 a6_ac_cs[0]=readl(a6_touch_gpio+87*4);
 for(i=0;i<7;i++)a6_ac_spi_before[i]=readl(a6_ac_spi+a6_ac_spi_offsets[i]);
 for(i=0;i<3;i++)a6_ac_iis_regs[0][i]=readl(a6_ac_iis+(i==0 ? 0 : i==1 ? 8 : 0x34));
 a6_ac_switch[0]=readl(a6_ai_switch+0x40);a6_ac_acs[0]=readl(a6_af_acs+0x10);
 /* Require idle bus and disabled serial streams before ownership. */
 if((a6_ac_cs[0]!=0x202 && a6_ac_cs[0]!=0x203) || readl(a6_ac_spi+8) ||
    a6_ac_spi_before[0] || a6_ac_spi_before[4] || a6_ac_spi_before[6] ||
    a6_ac_spi_before[1]!=8 || a6_ac_spi_before[2]!=3 ||
    a6_ac_spi_before[3]!=1 || a6_ac_spi_before[5] ||
    a6_ac_iis_regs[0][0]!=0x22 || a6_ac_iis_regs[0][1]!=0x01f80000 ||
    a6_ac_iis_regs[0][2]!=0x01f80000 || a6_ac_acs[0]>1 ||
    a6_ac_switch[0]==U32_MAX || (a6_ac_switch[0]&1)){ret=-EBUSY;goto restore;}
 clocked=true;writel(0,a6_af_acs+0x10);writel(0,a6_ac_iis+8);writel(0,a6_ac_iis+0x34);
 writel(0x134,a6_ac_iis);ret=a6_af_poll(a6_ac_iis,2,2);if(ret)goto restore;
 /* Stock aud0/pin0 MCLK-only switch route, emulated separately. */
 writel(a6_ac_switch[0]|1,a6_ai_switch+0x40);
 a6_ac_switch[1]=readl(a6_ai_switch+0x40);a6_ac_acs[1]=readl(a6_af_acs+0x10);
 for(i=0;i<3;i++)a6_ac_iis_regs[1][i]=readl(a6_ac_iis+(i==0 ? 0 : i==1 ? 8 : 0x34));
 if(a6_ac_switch[1]!=(a6_ac_switch[0]|1) || a6_ac_acs[1] ||
    a6_ac_iis_regs[1][0]!=0x136 || a6_ac_iis_regs[1][1] || a6_ac_iis_regs[1][2]){ret=-EIO;goto restore;}
 spi_changed=true;writel(0x203,a6_touch_gpio+87*4);
 a6_ac_cs[1]=readl(a6_touch_gpio+87*4);
 if(a6_ac_cs[1]!=0x203){ret=-EIO;goto restore;}
 for(j=0;j<3;j++){ret=a6_ac_read_reg(5,a6_ac_reply[j]);if(ret)goto restore;a6_ac_reads++;}
 if(a6_ac_reply[0][4]!=a6_ac_reply[1][4] || a6_ac_reply[0][4]!=a6_ac_reply[2][4] ||
    !a6_ac_reply[0][4] || a6_ac_reply[0][4]==255){ret=-ENODEV;goto restore;}
 for(j=0;j<13;j++){
  u8 reply[5];ret=a6_ac_read_reg(a6_ac_control_regs[j],reply);if(ret)goto restore;
  a6_ac_controls[j]=reply[4];a6_ac_control_reads++;
 }
 if(playback){ret=a6_ac_play_locked();}
restore:
 if(spi_changed) {
  writel(0,a6_ac_spi);writel(0x203,a6_touch_gpio+87*4);writel(0x40000f,a6_ac_spi+8);
  for(i=1;i<7;i++)writel(a6_ac_spi_before[i],a6_ac_spi+a6_ac_spi_offsets[i]);
  writel(a6_ac_spi_before[0],a6_ac_spi);writel(a6_ac_cs[0],a6_touch_gpio+87*4);
  a6_ac_cs[2]=readl(a6_touch_gpio+87*4);if(a6_ac_cs[2]!=a6_ac_cs[0])a6_ac_cleanup=-EUCLEAN;
  for(i=0;i<7;i++){a6_ac_spi_after[i]=readl(a6_ac_spi+a6_ac_spi_offsets[i]);if(a6_ac_spi_after[i]!=a6_ac_spi_before[i])a6_ac_cleanup=-EUCLEAN;}
  if(readl(a6_ac_spi+8))a6_ac_cleanup=-EUCLEAN;
 }
 if(clocked) {
  writel(a6_ac_switch[0],a6_ai_switch+0x40);writel(a6_ac_iis_regs[0][0],a6_ac_iis);
  if(a6_af_poll(a6_ac_iis,U32_MAX,a6_ac_iis_regs[0][0]))a6_ac_cleanup=-EUCLEAN;
  writel(a6_ac_iis_regs[0][1],a6_ac_iis+8);writel(a6_ac_iis_regs[0][2],a6_ac_iis+0x34);writel(a6_ac_acs[0],a6_af_acs+0x10);
  for(i=0;i<3;i++){a6_ac_iis_regs[2][i]=readl(a6_ac_iis+(i==0 ? 0 : i==1 ? 8 : 0x34));if(a6_ac_iis_regs[2][i]!=a6_ac_iis_regs[0][i])a6_ac_cleanup=-EUCLEAN;}
  a6_ac_switch[2]=readl(a6_ai_switch+0x40);a6_ac_acs[2]=readl(a6_af_acs+0x10);
  if(a6_ac_switch[2]!=a6_ac_switch[0] || a6_ac_acs[2]!=a6_ac_acs[0])a6_ac_cleanup=-EUCLEAN;
 }
 for(i=3;i-->0;) {
  if(gates[i])writel(a6_ac_gate[i][0],a6_touch_pmgr+a6_ac_gate_offsets[i]);
  if(gates[i] && a6_af_poll(a6_touch_pmgr+a6_ac_gate_offsets[i],U32_MAX,a6_ac_gate[i][0]))a6_ac_cleanup=-EUCLEAN;
  a6_ac_gate[i][2]=readl(a6_touch_pmgr+a6_ac_gate_offsets[i]);
 }
out:
 if(a6_ac_cleanup)ret=a6_ac_cleanup;
 a6_ac_result=ret;
 return ret;
}
static ssize_t a6_ac_run(struct kobject *k,struct kobj_attribute *a,const char *buf,size_t count)
{
 unsigned int tries;int ret;

#ifdef A6_AUDIO_ALSA
 return -EOPNOTSUPP; /* ALSA owns this candidate; diagnostic writes are disabled. */
#endif
 if(!capable(CAP_SYS_RAWIO))return -EPERM;
 if(!sysfs_streq(buf,"codec-id-enable-restore"))return -EINVAL;
 for(tries=0;tries<100;tries++){if(mutex_trylock(&a6_touch_lock))break;usleep_range(1000,2000);}
 if(tries==100)return -EBUSY;
 ret=a6_ac_execute_locked(false);mutex_unlock(&a6_touch_lock);return ret ? ret : count;
}
static ssize_t a6_ac_status(struct kobject *k,struct kobj_attribute *a,char *buf)
{
 unsigned int i;ssize_t n;
 if(!capable(CAP_SYS_RAWIO))return -EPERM;
 mutex_lock(&a6_touch_lock);
 n=sysfs_emit(buf,"A6_AUDIO_CODEC_CONTROL_V1 result=%d cleanup=%d reads=%u control_reads=%u\n",a6_ac_result,a6_ac_cleanup,a6_ac_reads,a6_ac_control_reads);
 for(i=0;i<3;i++)n+=sysfs_emit_at(buf,n,"codec_reply%u=%5phN gate%u=%08x/%08x/%08x iis%u=%08x,%08x,%08x\n",i,a6_ac_reply[i],i,a6_ac_gate[i][0],a6_ac_gate[i][1],a6_ac_gate[i][2],i,a6_ac_iis_regs[i][0],a6_ac_iis_regs[i][1],a6_ac_iis_regs[i][2]);
 n+=sysfs_emit_at(buf,n,"codec_cs87=%08x/%08x/%08x route40=%08x/%08x/%08x acs10=%08x/%08x/%08x\n",a6_ac_cs[0],a6_ac_cs[1],a6_ac_cs[2],a6_ac_switch[0],a6_ac_switch[1],a6_ac_switch[2],a6_ac_acs[0],a6_ac_acs[1],a6_ac_acs[2]);
 for(i=0;i<7;i++)n+=sysfs_emit_at(buf,n,"codec_spi_%02x=%08x/%08x\n",a6_ac_spi_offsets[i],a6_ac_spi_before[i],a6_ac_spi_after[i]);
 for(i=0;i<a6_ac_control_reads;i++)n+=sysfs_emit_at(buf,n,"codec_control_%04x=%02x\n",a6_ac_control_regs[i],a6_ac_controls[i]);
 n+=a6_ac_play_status(buf,n);
 mutex_unlock(&a6_touch_lock);return n;
}
static struct kobj_attribute a6_ac_run_attr=__ATTR(codec_run,0200,NULL,a6_ac_run);
static struct kobj_attribute a6_ac_status_attr=__ATTR(codec_status,0400,a6_ac_status,NULL);

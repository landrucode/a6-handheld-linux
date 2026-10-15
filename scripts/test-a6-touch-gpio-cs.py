#!/usr/bin/env python3
"""Run combined faults plus physical GPIO-CS ordering/readback failures."""
from pathlib import Path
import runpy,subprocess,tempfile
repo=Path(__file__).resolve().parents[1]
old=runpy.run_path(str(repo/'scripts/test-a6-touch-power-check.py'))
p=old['p'].replace('static unsigned ipart,', 'static int csfault;\nstatic bool csasserted;\nstatic unsigned ipart,')
p=p.replace('  if(v==spi+0x10)spiwords++;', '''  if(v==spi+0x10){
   assert(*(u32*)(gpio+A6_TOUCH_CS)==0x202);
   assert(*(u32*)(gpio+A6_TOUCH_RESET)==0x203);
   assert(*(u32*)(spi+0xc)==3); /* No internal-CS assertion. */
   assert(pmu[0x22]==0xef && pmu[0x23]==0xed);
   spiwords++;
  }
  if(v==gpio+A6_TOUCH_CS){
   assert(value==0x202 || value==0x203);
   if(value==0x203 && !csasserted && csfault==1)return;
   if(value==0x202 && *(u32*)(gpio+A6_TOUCH_RESET)==0x203){
    assert(!csasserted);csasserted=true;
    if(csfault==2)return;
   }
   if(value==0x203 && csasserted){
    assert(!running);if(csfault==3)return;
   }
  }''')
source='#define A6_TOUCH_GPIO_CS 1\n'+old['source']
tests=old['tests'].replace(' setup(0);memset(i2c', ' csfault=0;csasserted=false;a6_gpio_cs_active=false;\n a6_gpio_cs_idle=a6_gpio_cs_asserted=a6_gpio_cs_released=0;\n setup(0);memset(i2c')
tests=tests.replace('"check-with-power",16', '"check-with-gpio-cs",18').replace(')==16)',')==18)')
tests=tests.replace(' puts("PASS actual power/PWM/CHECK:', ''' for(int f=1;f<=3;f++){
  init(0,0);csfault=f;
  int ret=a6_check_run_store(NULL,NULL,"check-with-gpio-cs",18);
  assert(ret==(f==3 ? -EUCLEAN : -EIO));
  assert(a6_power_restored && a6_pwm_probe_restored);
  assert(a6_check_restored==(f!=3));
  assert(spiwords==(f==3 ? 4 : 0));
  assert(*(u32*)(gpio+A6_TOUCH_CS)==0x202 && *(u32*)(gpio+A6_TOUCH_RESET)==0x202);
 }
 init(0,0);assert(a6_check_run_store(NULL,NULL,"check-with-gpio-cs",18)==18);
 assert(a6_gpio_cs_idle==0x203 && a6_gpio_cs_asserted==0x202 && a6_gpio_cs_released==0x203);
 puts("PASS GPIO-CS readbacks/order and actual power/PWM/CHECK:''')
with tempfile.TemporaryDirectory(prefix='a6-gpio-cs-test-') as tmp:
 c=Path(tmp)/'test.c';c.write_text(p+source+old['setup']+tests);exe=Path(tmp)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)

#!/usr/bin/env python3
"""Execute the real PMU allowlist and collector against refusal/readback cases."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'kernel/platform/a6-touch-power-check.inc').read_text()
start = source.index('static int a6_power_xfer_scoped')
end = source.index('\tif (log && a6_power_transactions', start)
guard = source[start:end] + '\nreturn 123;\n}\n'
wrapper = source[source.index('static int a6_power_combo_reset'):source.index('#endif\n#ifdef A6_D1972_STOCK_OFF_CANDIDATE\n/* One bounded FIFO')]
common = '''#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <assert.h>
typedef uint8_t u8; typedef uint32_t u32;
#define A6_POWER_XEN 1
#define A6_POWER_TX 2
static bool a6_power_saved;
'''
read_helper = source[source.index('static bool a6_power_shutdown_read_reg'):source.index('#endif\n#ifdef A6_D1972_STOCK_OFF_CANDIDATE')]
for enabled in (False, True):
    defines = '#define A6_D1972_POLICY 1\n' + ('#define A6_WIFI_EHCI_ENUM 1\n' if enabled else '')
    main = '''int main(void) {
unsigned int n=0; u8 v;
for (int x=0;x<256;x++) {
 v=x;
 assert(a6_power_xfer_scoped(0x72,&v,true,false,false,&n)==-EINVAL);
 assert(a6_power_xfer_scoped(0x71,&v,true,false,true,&n)==-EINVAL);
 assert(a6_power_xfer_scoped(0x72,&v,true,true,true,&n)==-EINVAL);
 assert(a6_power_xfer_scoped(0x72,&v,true,false,true,&n)==EXPECTED);
}
assert(n==0);
}'''.replace('EXPECTED', '(x<32 ? 123 : -EINVAL)' if enabled else '-EINVAL')
    with tempfile.TemporaryDirectory() as directory:
        p = Path(directory)
        (p/'test.c').write_text(common+defines+read_helper+guard+main)
        subprocess.run(['cc','-std=c99',str(p/'test.c'),'-o',str(p/'test')],check=True)
        subprocess.run([str(p/'test')],check=True)
# Dedicated wrapper permits precisely saved/pulse bytes.
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    main='''int main(void) { unsigned int n=0;
for(int saved=0;saved<256;saved++) for(int value=0;value<256;value++) {
bool allowed=saved<32 && (value==saved || value==(saved&0x1d) || value==((saved&0x1d)|2));
assert(a6_power_combo_reset(saved,value,&n)==(allowed ? 123 : -EINVAL));
} }'''
    stub='static int a6_power_xfer_scoped(u8 r,u8 *v,bool w,bool l,bool c,unsigned int *n) { assert(r==0x72 && w && !l && c); return 123; }\n'
    (p/'test.c').write_text(common+stub+wrapper+main)
    subprocess.run(['cc',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
spec=importlib.util.spec_from_file_location('collector',root/'scripts/a6-capture-wifi-ehci-enum.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
legacy='A6_WIFI_EHCI_ENUM_V1 attempted=1 result=-22 restore=-22 stage=2'
assert m.classify(legacy)=='software_write_refused_restoration_unverified'
base='A6_WIFI_EHCI_ENUM_V2 attempted=1 result=0 restore=0 stage=4 vid=0a5c reset72=09 reset72_after=09 reset_readback=0 gate_before=00000200 gate_after=00000200 phy8=00000000 phy8_after=00000000 usb_ctl=c0000080 usb_ctl_after=c0000080 pmu_submitted=2 pmu_completed=2 pmu_restore_submitted=1 pmu_restore_completed=1'
assert m.classify(base)=='usb_device_enumerated'
assert m.classify(base.replace('result=0','result=-110').replace('vid=0a5c','vid=0000'))=='no_enumeration_restored'
for old,new in [('reset72_after=09','reset72_after=0b'),('gate_after=00000200','gate_after=000002ff'),('phy8_after=00000000','phy8_after=00000020'),('usb_ctl_after=c0000080','usb_ctl_after=c0000084'),('restore=0','restore=-5')]:
    assert m.classify(base.replace(old,new))=='restoration_failed'
assert m.classify(base.replace('restore=0','restore=-22').replace('pmu_restore_submitted=1','pmu_restore_submitted=0'))=='software_restore_write_refused_restoration_unverified'
assert m.classify(base.replace('stage=4','stage=0').replace('restore=0','restore=-22'))=='preflight_refused'
assert m.classify(base.replace('reset_readback=0 ',' '))=='restoration_unverified'
assert m.classify(base.replace('result=0','result=-22').replace('pmu_submitted=2','pmu_submitted=0'))=='software_write_refused_restored'
assert m.classify('A6_EHCI_PROGRESS_V1 phase=2 elapsed=0 irq_calls=1\ntrial_inflight=1\r\n')=='trial_inflight_restoration_unverified'
assert m.classify('Internal error: Oops - BUG: 7 [#1] SMP THUMB2\ntrial_inflight=1')=='kernel_oops_restoration_unverified'
try: m.classify('')
except RuntimeError: pass
else: raise AssertionError('missing status accepted')
print('PMU build gates, 65536 reset value pairs and collector restoration cases passed')

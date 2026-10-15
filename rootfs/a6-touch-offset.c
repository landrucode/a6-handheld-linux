/* Experimental RAM-session correction from Q/P/Space taps; not full-screen calibration. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <string.h>
struct libinput_device;
int libinput_device_config_calibration_set_matrix(struct libinput_device *d,const float m[6]) {
 int (*set)(struct libinput_device *,const float *)=dlsym(RTLD_NEXT,"libinput_device_config_calibration_set_matrix");
 const char *(*name)(struct libinput_device *)=dlsym(RTLD_NEXT,"libinput_device_get_name");
 if(!set || !name)return 2;
 if(!strcmp(name(d),"A6 N42 native touchscreen") && m[0]==1 && m[1]==0 && m[2]==0 && m[3]==0 && m[4]==-1 && m[5]==1) {
  const float corrected[6]={1,0,25.0f/640.0f,0,-1,1-47.0f/1136.0f};
  return set(d,corrected);
 }
 return set(d,m);
}

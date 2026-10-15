/* Five-point raw-evdev calibration overlay. No input grab or coordinate shim. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include <cairo/cairo.h>
#include <linux/input.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <errno.h>
static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct zwlr_layer_shell_v1 *shell;
static struct wl_surface *surface;
static struct zwlr_layer_surface_v1 *layer;
static struct wl_buffer *buffer;
static void *pixels;
static int width,height,point,finished;
static const double targets[5][2]={{.1,.1},{.9,.1},{.9,.9},{.1,.9},{.5,.5}};
static long long next_tap;
static long long milliseconds(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1000LL+t.tv_nsec/1000000;}
static void die(const char *s){perror(s);exit(1);}
static void draw(void) {
 cairo_surface_t *cs=cairo_image_surface_create_for_data(pixels,CAIRO_FORMAT_ARGB32,width,height,width*4);
 cairo_t *c=cairo_create(cs);cairo_set_source_rgb(c,.04,.04,.04);cairo_paint(c);
 cairo_set_source_rgb(c,1,1,1);cairo_select_font_face(c,"sans",CAIRO_FONT_SLANT_NORMAL,CAIRO_FONT_WEIGHT_NORMAL);cairo_set_font_size(c,24);
 char text[100];snprintf(text,sizeof(text),"Tap cross %d of 5, then lift your finger",point+1);cairo_move_to(c,30,height*.4);cairo_show_text(c,text);
 double x=width*targets[point][0],y=height*targets[point][1];
 cairo_set_source_rgb(c,1,.3,.1);cairo_set_line_width(c,3);cairo_arc(c,x,y,24,0,6.283185307);cairo_move_to(c,x-35,y);cairo_line_to(c,x+35,y);cairo_move_to(c,x,y-35);cairo_line_to(c,x,y+35);cairo_stroke(c);
 cairo_destroy(c);cairo_surface_destroy(cs);wl_surface_attach(surface,buffer,0,0);wl_surface_damage(surface,0,0,width,height);wl_surface_commit(surface);
}
static void configure(void *data,struct zwlr_layer_surface_v1 *ls,uint32_t serial,uint32_t w,uint32_t h){
 (void)data;zwlr_layer_surface_v1_ack_configure(ls,serial);
 if(buffer){if(w!=(uint32_t)width||h!=(uint32_t)height){fprintf(stderr,"Display resized during calibration\n");exit(1);}return;}
 if(!w||!h||w>4096||h>4096){fprintf(stderr,"Invalid full-screen dimensions\n");exit(1);}
 width=w;height=h;int fd=memfd_create("a6-calibration",MFD_CLOEXEC);if(fd<0||ftruncate(fd,width*height*4))die("shm");
 pixels=mmap(NULL,width*height*4,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(pixels==MAP_FAILED)die("mmap");
 struct wl_shm_pool *pool=wl_shm_create_pool(shm,fd,width*height*4);buffer=wl_shm_pool_create_buffer(pool,0,width,height,width*4,WL_SHM_FORMAT_ARGB8888);wl_shm_pool_destroy(pool);close(fd);draw();next_tap=milliseconds()+700;
}
static void closed(void *data,struct zwlr_layer_surface_v1 *ls){(void)data;(void)ls;finished=1;}
static const struct zwlr_layer_surface_v1_listener ll={configure,closed};
static void global(void *data,struct wl_registry *r,uint32_t id,const char *name,uint32_t version){
 (void)data;(void)version;
 if(!strcmp(name,"wl_compositor"))compositor=wl_registry_bind(r,id,&wl_compositor_interface,1);
 if(!strcmp(name,"wl_shm"))shm=wl_registry_bind(r,id,&wl_shm_interface,1);
 if(!strcmp(name,"zwlr_layer_shell_v1"))shell=wl_registry_bind(r,id,&zwlr_layer_shell_v1_interface,1);
}
static void removed(void *d,struct wl_registry *r,uint32_t n){(void)d;(void)r;(void)n;}
static const struct wl_registry_listener rl={global,removed};
int main(int argc,char **argv){
 if(argc!=3){fprintf(stderr,"Usage: a6-touch-calibrate /dev/input/eventN private-samples.jsonl\n");return 2;}
 int input=open(argv[1],O_RDONLY|O_NONBLOCK|O_CLOEXEC);if(input<0)die("input");
 char name[128]={0};if(ioctl(input,EVIOCGNAME(sizeof(name)),name)<0||strcmp(name,"A6 N42 native touchscreen")){fprintf(stderr,"Wrong input device\n");return 1;}
 struct input_absinfo ax,ay;if(ioctl(input,EVIOCGABS(ABS_MT_POSITION_X),&ax)||ioctl(input,EVIOCGABS(ABS_MT_POSITION_Y),&ay))die("axes");
 int out=open(argv[2],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(out<0)die("samples");FILE *log=fdopen(out,"w");
 display=wl_display_connect(NULL);if(!display)die("Wayland");struct wl_registry *reg=wl_display_get_registry(display);wl_registry_add_listener(reg,&rl,NULL);wl_display_roundtrip(display);
 if(!compositor||!shm||!shell){fprintf(stderr,"Missing layer-shell\n");return 1;}
 surface=wl_compositor_create_surface(compositor);layer=zwlr_layer_shell_v1_get_layer_surface(shell,surface,NULL,ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY,"a6-calibration");
 zwlr_layer_surface_v1_set_anchor(layer,15);zwlr_layer_surface_v1_set_size(layer,0,0);zwlr_layer_surface_v1_set_exclusive_zone(layer,-1);zwlr_layer_surface_v1_set_keyboard_interactivity(layer,0);zwlr_layer_surface_v1_add_listener(layer,&ll,NULL);wl_surface_commit(surface);
 int slot=0,active=0,x=0,y=0,have_x=0,have_y=0,released=0;long long deadline=milliseconds()+180000;
 while(!finished&&milliseconds()<deadline){
  while(wl_display_prepare_read(display)!=0)if(wl_display_dispatch_pending(display)<0)die("dispatch");
  short events=POLLIN;if(wl_display_flush(display)<0){if(errno==EAGAIN)events|=POLLOUT;else{wl_display_cancel_read(display);die("flush");}}
  struct pollfd fds[2]={{wl_display_get_fd(display),events,0},{input,POLLIN,0}};int ready=poll(fds,2,1000);
  if(ready<0){wl_display_cancel_read(display);if(errno==EINTR)continue;die("poll");}
  if(fds[0].revents&POLLIN){if(wl_display_read_events(display)<0)die("read");}else wl_display_cancel_read(display);
  if(fds[0].revents&(POLLERR|POLLHUP))die("Wayland closed");if(wl_display_dispatch_pending(display)<0)die("dispatch");
  struct input_event e;
  while(read(input,&e,sizeof(e))==sizeof(e)){
   if(e.type==EV_SYN&&e.code==SYN_DROPPED){fprintf(stderr,"Input overflow: restart calibration\n");return 1;}
   if(e.type==EV_ABS&&e.code==ABS_MT_SLOT)slot=e.value;
   if(e.type==EV_ABS&&slot==0){
    if(e.code==ABS_MT_TRACKING_ID){if(e.value>=0){active=1;have_x=have_y=0;}else if(active){released=1;active=0;}}
    if(e.code==ABS_MT_POSITION_X){x=e.value;have_x=1;}
    if(e.code==ABS_MT_POSITION_Y){y=e.value;have_y=1;}
   }
   if(e.type==EV_SYN&&e.code==SYN_REPORT&&released){
    released=0;if(!buffer||!have_x||!have_y||milliseconds()<next_tap)continue;
    fprintf(log,"{\"point\":%d,\"raw\":[%.9f,%.9f],\"target\":[%.9f,%.9f],\"screen\":[%d,%d]}\n",point,(x-ax.minimum)/(double)(ax.maximum-ax.minimum),(y-ay.minimum)/(double)(ay.maximum-ay.minimum),targets[point][0],targets[point][1],width,height);fflush(log);
    if(++point==5){finished=1;break;}draw();next_tap=milliseconds()+700;
   }
  }
 }
 fclose(log);zwlr_layer_surface_v1_destroy(layer);wl_surface_destroy(surface);wl_display_flush(display);wl_display_disconnect(display);close(input);
 if(point!=5){fprintf(stderr,"Incomplete calibration\n");return 1;}puts("FIVE_POINTS_CAPTURED");return 0;
}

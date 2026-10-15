/* Small unprivileged touch launcher: no root shell or network listener. */
#include <wayland-client.h>
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include <cairo/cairo.h>
#include <json/json.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <poll.h>
#include <errno.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sstream>
#include <regex>
#include <vector>
static wl_display *display;
static wl_compositor *compositor;
static wl_shm *shm;
static zwlr_layer_shell_v1 *shell;
static wl_seat *seat;
static wl_surface *surface;
static wl_buffer *buffer;
static void *pixels;
static int width,height;
static bool done=false;
static int selected=-1,touch_id=-1,busy_button=-1;
static int completion[2]={-1,-1};
static std::string browser_status;
static unsigned bar_colour,button_colour,focus_colour,text_colour,pressure_colour;
static bool theme_colour(const char *key,unsigned &value){
 const char *s=getenv(key);if(!s||strlen(s)!=6||strspn(s,"0123456789abcdefABCDEF")!=6)return false;
 value=strtoul(s,nullptr,16);return true;
}
static void colour(cairo_t *c,unsigned value){cairo_set_source_rgb(c,((value>>16)&255)/255.0,((value>>8)&255)/255.0,(value&255)/255.0);}

static const char *labels[]={"Terminal","Browser","Next","Close","Keys"};
static Json::Value clients(){
 FILE *f=popen("timeout 8 hyprctl clients -j 2>/dev/null","r");if(!f)return Json::Value();
 std::string data;char b[512];while(fgets(b,sizeof(b),f)&&data.size()<65536)data+=b;pclose(f);
 Json::Value result;Json::CharReaderBuilder builder;std::string error;std::istringstream in(data);
 if(!Json::parseFromStream(builder,in,&result,&error)||!result.isArray())return Json::Value();return result;
}
static void focus(const std::string &address){
 if(!std::regex_match(address,std::regex("0x[0-9a-fA-F]+")))return;
 // Explicit targets avoid active-window races; one IPC batch also avoids
 // repeatedly loading hyprctl on this software-rendered RAM desktop.
 std::string batch;
 for(const auto &client:clients()){
  std::string other=client["address"].asString();
  if(!std::regex_match(other,std::regex("0x[0-9a-fA-F]+")))continue;
  batch+="dispatch hl.dsp.window.fullscreen({mode=\"maximized\",action=\"unset\",window=\"address:"+other+"\"}); ";
 }
 batch+="dispatch hl.dsp.focus({window=\"address:"+address+"\"}); ";
 batch+="dispatch hl.dsp.window.fullscreen({mode=\"maximized\",action=\"set\",window=\"address:"+address+"\"})";
 std::string command="timeout 12 hyprctl --batch '"+batch+"' >/dev/null 2>&1";
 int rc=system(command.c_str());(void)rc;

}
static void action(int button){
 if(button<0||button>4)return;
 if(button==0||button==1){
  const auto list=clients();const char *cls=button==0?"foot":"epiphany";
  for(const auto &client:list){std::string c=client["class"].asString();if(c==cls||c=="org.gnome.Epiphany"){if(button==0&&c!="foot")continue;focus(client["address"].asString());return;}}
  if(button==0){int rc=system("foot /bin/bash >/tmp/a6-foot-user.private.log 2>&1 & /usr/local/bin/a6-focus-app.sh foot");(void)rc;}else{int fd=open("/run/a6-app-control",O_WRONLY|O_NONBLOCK|O_CLOEXEC);if(fd>=0){const char request[]="browser\n";ssize_t n=write(fd,request,sizeof(request)-1);(void)n;close(fd);}}
 }else if(button==2){
  auto list=clients();if(list.empty())return;
  FILE *f=popen("timeout 8 hyprctl activewindow -j 2>/dev/null","r");std::string data;char b[512];if(f){while(fgets(b,sizeof(b),f)&&data.size()<65536)data+=b;pclose(f);}
  Json::Value current;Json::CharReaderBuilder builder;std::string error;std::istringstream in(data);Json::parseFromStream(builder,in,&current,&error);
  unsigned index=0;for(unsigned i=0;i<list.size();i++)if(list[i]["address"]==current["address"]){index=(i+1)%list.size();break;}focus(list[index]["address"].asString());
 }else if(button==3){int rc=system("hyprctl dispatch 'hl.dsp.window.close()' >/dev/null 2>&1");(void)rc;}
 else{FILE *f=fopen("/home/a6/wvkbd-test.pid","r");long pid=0;if(f){if(fscanf(f,"%ld",&pid)==1&&pid>1){char path[64],name[64]={0};snprintf(path,sizeof(path),"/proc/%ld/comm",pid);FILE *c=fopen(path,"r");if(c){if(fgets(name,sizeof(name),c)&&!strcmp(name,"wvkbd-native\n"))kill(pid,SIGRTMIN);fclose(c);}}fclose(f);}}
}
static void draw(){
 if(!buffer)return;cairo_surface_t *cs=cairo_image_surface_create_for_data((unsigned char*)pixels,CAIRO_FORMAT_ARGB32,width,height,width*4);cairo_t *c=cairo_create(cs);
 cairo_select_font_face(c,"sans",CAIRO_FONT_SLANT_NORMAL,CAIRO_FONT_WEIGHT_BOLD);cairo_set_font_size(c,22);
 colour(c,bar_colour);cairo_paint(c);
 for(int i=0;i<5;i++){colour(c,i==selected?focus_colour:button_colour);cairo_rectangle(c,i*width/5.0,0,width/5.0-2,height);cairo_fill(c);colour(c,i==1&&browser_status=="pressure"?pressure_colour:text_colour);const char *label=i==busy_button?"Working":(i==1&&browser_status=="starting"?"Starting":labels[i]);cairo_text_extents_t ext;cairo_text_extents(c,label,&ext);cairo_move_to(c,(i+.5)*width/5.0-ext.width/2-ext.x_bearing,height/2.0-ext.height/2-ext.y_bearing);cairo_show_text(c,label);}
 cairo_destroy(c);cairo_surface_destroy(cs);wl_surface_attach(surface,buffer,0,0);wl_surface_damage(surface,0,0,width,height);wl_surface_commit(surface);
}
static void configure(void*,zwlr_layer_surface_v1 *ls,uint32_t serial,uint32_t w,uint32_t h){
 zwlr_layer_surface_v1_ack_configure(ls,serial);if(buffer)return;if(!w||!h||w>4096||h>512)exit(1);width=w;height=h;
 int fd=memfd_create("a6-panel",MFD_CLOEXEC);if(fd<0||ftruncate(fd,width*height*4))exit(1);pixels=mmap(nullptr,width*height*4,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);if(pixels==MAP_FAILED)exit(1);
 auto pool=wl_shm_create_pool(shm,fd,width*height*4);buffer=wl_shm_pool_create_buffer(pool,0,width,height,width*4,WL_SHM_FORMAT_ARGB8888);wl_shm_pool_destroy(pool);close(fd);draw();
}
static void closed(void*,zwlr_layer_surface_v1*){done=true;}
static const zwlr_layer_surface_v1_listener ll={configure,closed};
static void down(void*,wl_touch*,uint32_t,uint32_t,wl_surface *s,int32_t id,wl_fixed_t x,wl_fixed_t){if(s!=surface||touch_id!=-1)return;touch_id=id;selected=int(wl_fixed_to_double(x)*5/width);draw();}
static void up(void*,wl_touch*,uint32_t,uint32_t,int32_t id){
 if(id!=touch_id)return;int b=selected;selected=-1;touch_id=-1;
 if(busy_button!=-1||(b==1&&browser_status=="starting")){draw();return;}
 busy_button=b;draw();wl_display_flush(display);
 pid_t child=fork();
 if(child==0){signal(SIGCHLD,SIG_DFL);close(wl_display_get_fd(display));close(completion[0]);action(b);char finished=1;ssize_t n=write(completion[1],&finished,1);(void)n;_exit(0);}
 if(child<0){busy_button=-1;draw();}
}
static void motion(void*,wl_touch*,uint32_t,int32_t,wl_fixed_t,wl_fixed_t){}
static void frame(void*,wl_touch*){}
static void cancel(void*,wl_touch*){selected=-1;touch_id=-1;draw();}
static void shape(void*,wl_touch*,int32_t,wl_fixed_t,wl_fixed_t){}
static void orientation(void*,wl_touch*,int32_t,wl_fixed_t){}
static const wl_touch_listener tl={down,up,motion,frame,cancel,shape,orientation};
static void capabilities(void*,wl_seat *s,uint32_t caps){if(caps&WL_SEAT_CAPABILITY_TOUCH){auto t=wl_seat_get_touch(s);wl_touch_add_listener(t,&tl,nullptr);}}
static void seat_name(void*,wl_seat*,const char*){}
static const wl_seat_listener sl={capabilities,seat_name};
static void global(void*,wl_registry *r,uint32_t id,const char *name,uint32_t version){
 if(!strcmp(name,"wl_compositor"))compositor=(wl_compositor*)wl_registry_bind(r,id,&wl_compositor_interface,1);
 if(!strcmp(name,"wl_shm"))shm=(wl_shm*)wl_registry_bind(r,id,&wl_shm_interface,1);
 if(!strcmp(name,"zwlr_layer_shell_v1"))shell=(zwlr_layer_shell_v1*)wl_registry_bind(r,id,&zwlr_layer_shell_v1_interface,1);
 if(!strcmp(name,"wl_seat")){seat=(wl_seat*)wl_registry_bind(r,id,&wl_seat_interface,version<5?version:5);wl_seat_add_listener(seat,&sl,nullptr);}
}
static void removed(void*,wl_registry*,uint32_t){}
static const wl_registry_listener rl={global,removed};
int main(int argc,char **argv){
 if(getuid()!=1000)return 1;
 if(argc==3&&!strcmp(argv[1],"--focus")){
  std::string cls=argv[2];if(cls!="foot"&&cls!="epiphany")return 2;
  for(int n=0;n<60;n++){
   for(const auto &client:clients())if(client["class"].asString()==cls||(cls=="epiphany"&&client["class"].asString()=="org.gnome.Epiphany")){focus(client["address"].asString());return 0;}
   sleep(1);
  }return 1;
 }
 if(argc!=1)return 2;
 if(!theme_colour("A6_BG_ALT",bar_colour)||!theme_colour("A6_SURFACE",button_colour)||!theme_colour("A6_LAVENDER",focus_colour)||!theme_colour("A6_FG",text_colour)||!theme_colour("A6_ROSE",pressure_colour))return 1;
 if(pipe2(completion,O_CLOEXEC|O_NONBLOCK))return 1;signal(SIGCHLD,SIG_IGN);display=wl_display_connect(nullptr);if(!display)return 1;auto registry=wl_display_get_registry(display);wl_registry_add_listener(registry,&rl,nullptr);wl_display_roundtrip(display);if(!compositor||!shm||!shell||!seat)return 1;
 surface=wl_compositor_create_surface(compositor);auto layer=zwlr_layer_shell_v1_get_layer_surface(shell,surface,nullptr,ZWLR_LAYER_SHELL_V1_LAYER_TOP,"a6-panel");zwlr_layer_surface_v1_set_anchor(layer,ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP|ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT|ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT);zwlr_layer_surface_v1_set_size(layer,0,72);zwlr_layer_surface_v1_set_exclusive_zone(layer,72);zwlr_layer_surface_v1_set_keyboard_interactivity(layer,0);zwlr_layer_surface_v1_add_listener(layer,&ll,nullptr);wl_surface_commit(surface);
 while(!done){
  while(wl_display_prepare_read(display)!=0)if(wl_display_dispatch_pending(display)<0){done=true;break;}
  if(done)break;
  int flushed=wl_display_flush(display);
  if(flushed<0&&errno!=EAGAIN){wl_display_cancel_read(display);break;}
  pollfd fds[2]={{wl_display_get_fd(display),short(POLLIN|(flushed<0?POLLOUT:0)),0},{completion[0],POLLIN,0}};
  int ready=poll(fds,2,500);
  if(ready<0){wl_display_cancel_read(display);if(errno==EINTR)continue;break;}
  if(fds[0].revents&POLLIN){if(wl_display_read_events(display)<0)break;}
  else wl_display_cancel_read(display);
  if(fds[0].revents&(POLLERR|POLLHUP))break;
  if(wl_display_dispatch_pending(display)<0)break;
  if(fds[1].revents&POLLIN){char buf[32];while(read(completion[0],buf,sizeof(buf))>0){}busy_button=-1;draw();}
  char state[32]={0};FILE *status=fopen("/run/a6-browser-status","r");if(status){if(fgets(state,sizeof(state),status)){state[strcspn(state,"\n")]=0;}fclose(status);}
  if(browser_status!=state){browser_status=state;draw();}
 }
 wl_display_disconnect(display);return 0;
}

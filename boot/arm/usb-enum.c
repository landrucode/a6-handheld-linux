/* Bare-metal EP0 enumeration proof, NOT a Linux USB gadget or a shell.
 * DWC2 PIO register semantics checked against Linux dwc2/hw.h, gadget.c
 * and TinyUSB's Synopsys dcd_dwc2.c. CPU IRQs stay masked; DMA disabled.
 */
#include <stdint.h>
#include <stddef.h>
#include "usb-enum-protocol.h"
#define BIT(n) (1u<<(n))
#define BASE 0x36100000u
#define GAHB 0x008
#define GUSB 0x00c
#define GRST 0x010
#define GINT 0x014
#define GMSK 0x018
#define RXPOP 0x020
#define RXFSIZ 0x024
#define TXFSIZ 0x028
#define DCFG 0x800
#define DCTL 0x804
#define DSTS 0x808
#define INCTL 0x900
#define ININT 0x908
#define INSIZ 0x910
#define TXSPACE 0x918
#define OUTCTL 0xb00
#define OUTINT 0xb08
#define OUTSIZ 0xb10
#define FIFO 0x1000
#define ACTIVE BIT(15)
#define ENABLE BIT(31)
#define CNAK BIT(26)
#define STALL BIT(21)
static uint32_t trace[13], display[13];
static uint32_t render_row, frame_color;
static uint8_t setup[8], setup_valid, configuration;
static int pending_address=-1, pending_config=-1;
#ifdef USB_LINK_STATE
/* Observation only: before/after attach and first reset-handler invocation. */
static uint32_t link_dctl[4];
#endif
#ifdef USB_PHY_ATTACH_GATE
static uint32_t attach_uvld[2];
#endif
static inline void barrier(void) { __asm__ volatile("dsb sy" ::: "memory"); }
static inline uint32_t rd(unsigned r) { return *(volatile uint32_t *)(BASE+r); }
static inline void wr(unsigned r,uint32_t v) { *(volatile uint32_t *)(BASE+r)=v; barrier(); }
static uint32_t ticks(void) { return *(volatile uint32_t *)0x3f200020; }
static int delay(uint32_t t) {
    uint32_t start=ticks();
    for(unsigned n=0;n<0x1000000;n++) if((uint32_t)(ticks()-start)>=t) return 1;
    return 0;
}
static int wait_bits(unsigned reg,uint32_t mask,uint32_t expected) {
    uint32_t start=ticks();
    for(unsigned n=0;n<0x1000000;n++) {
        if((rd(reg)&mask)==expected) return 1;
        if((uint32_t)(ticks()-start)>2400000) break;
    }
    return 0;
}
/* Draw one scanline per polling iteration, never a full frame in a handler. */
static void draw_line(void) {
    volatile uint32_t *meta=(volatile uint32_t *)0x83fff000;
    uint32_t width=meta[2]>>2, count=meta[1], row=render_row;
    if(row==0) {
#ifdef USB_LINK_STATE
        display[0]=(trace[0]&255)|((trace[1]&255)<<8)|
                   ((trace[2]&255)<<16)|((trace[3]&255)<<24);
        for(unsigned i=0;i<4;i++) display[i+1]=link_dctl[i];
#ifdef USB_PHY_ATTACH_GATE
        display[3]=attach_uvld[0];
        display[4]=attach_uvld[1];
#endif
        display[5]=rd(DCTL);
        display[6]=rd(GUSB);
        display[7]=rd(DCFG);
        display[8]=rd(0);
        display[9]=rd(0xe00);
        display[10]=*(volatile uint32_t *)0x36000000;
        display[11]=*(volatile uint32_t *)0x36000008;
        display[12]=trace[11];
#else
        for(unsigned i=0;i<13;i++) display[i]=trace[i];
#endif
        frame_color=trace[11]?0xff0000:(configuration?0x00ff00:0x00ffff);
    }
    uint32_t offset=row*width;
    if(offset>=count) { render_row=0; return; }
    volatile uint32_t *fb=(volatile uint32_t *)(uintptr_t)meta[0];
    unsigned band=(row>>6)&15;
    for(unsigned x=0;x<width && offset+x<count;x++) {
        uint32_t color=((x>>6)^(row>>6))&1?0xffffff:frame_color;
        if(band>=1 && band<=13) {
            unsigned bit=x>>4;
            color=bit<32 && (display[band-1]&BIT(bit))?0xffffff:0;
        }
        fb[offset+x]=color;
    }
    render_row++;
}
__attribute__((noreturn)) static void fail(unsigned code) {
    trace[11]=code; trace[9]=rd(GINT); trace[10]=rd(DSTS);
    /* Stop presenting an unserviced device to the host after a fatal error. */
    wr(DCTL,rd(DCTL)|BIT(1));
    for(;;) draw_line();
}
static void arm_out(void) {
    wr(OUTSIZ,(3u<<29)|BIT(19)|64);
    wr(OUTCTL,ACTIVE|ENABLE|CNAK);
}
static void flush(unsigned tx) {
    wr(GRST,tx?((16u<<6)|BIT(5)):BIT(4));
    if(!wait_bits(GRST,tx?BIT(5):BIT(4),0)) fail(tx?0x21:0x22);
}
static void reset_ep0(void) {
    setup_valid=0; configuration=0; pending_address=pending_config=-1;
    trace[7]=trace[8]=0;
    wr(DCFG,rd(DCFG)&~(127u<<4));
    wr(ININT,0xffffffff); wr(OUTINT,0xffffffff);
    wr(0x810,BIT(0)|BIT(1)|BIT(3));
    wr(0x814,BIT(0)|BIT(3)|BIT(15));
    wr(0x81c,BIT(0)|BIT(16));
    wr(0x834,0);
    flush(1); flush(0);
    /* 128 RX + 64 EP0 TX words, within observed 2024-word FIFO. */
    wr(RXFSIZ,128); wr(TXFSIZ,(64u<<16)|128);
    wr(INCTL,ACTIVE|BIT(27));
    arm_out();
    wr(DCTL,(rd(DCTL)&~(BIT(7)|BIT(9)))|BIT(8)|BIT(10));
}
static void send_reply(const struct control_reply *r) {
    /* Abort a prior IN transfer if superseded by a new SETUP. */
    if(rd(INCTL)&ENABLE) {
        wr(INCTL,rd(INCTL)|BIT(27)|BIT(30));
        if(!wait_bits(ININT,BIT(1),BIT(1))) fail(0x23);
        wr(ININT,BIT(1));
        flush(1);
    }
    wr(ININT,0xffffffff);
    arm_out(); /* Receive OUT status or the next SETUP, including after stalls. */
    pending_address=pending_config=-1;
    if(r->action==REPLY_STALL) { wr(INCTL,ACTIVE|STALL); return; }
    if(r->action==REPLY_ADDRESS) {
#ifdef USB_ADDRESS_BEFORE_STATUS
        /* Match Linux dwc2 gadget.c and TinyUSB dcd_set_address ordering. */
        wr(DCFG,(rd(DCFG)&~(127u<<4))|((uint32_t)r->value<<4));
        trace[7]=r->value;
#else
        pending_address=r->value;
#endif
    }
    if(r->action==REPLY_CONFIG) pending_config=r->value;
    unsigned n=r->length, words=(n+3)>>2;
    uint32_t start=ticks(); unsigned limit=0x1000000;
    while((rd(TXSPACE)&0xffff)<words) {
        if(! --limit || (uint32_t)(ticks()-start)>2400000) fail(0x24);
    }
    wr(INSIZ,BIT(19)|n);
    wr(INCTL,ACTIVE|CNAK|ENABLE);
    for(unsigned i=0;i<words;i++) {
        uint32_t v=0;
        for(unsigned j=0;j<4;j++) if(i*4+j<n) v|=(uint32_t)r->data[i*4+j]<<(8*j);
        wr(FIFO,v);
    }
}
static void dispatch_setup(void) {
    if(!setup_valid) { trace[11]=0x31; return; }
    setup_valid=0; trace[3]++;
    trace[4]=(uint32_t)setup[0]|((uint32_t)setup[1]<<8)|((uint32_t)le16(setup+2)<<16);
    trace[5]=le16(setup+4)|((uint32_t)le16(setup+6)<<16);
    struct control_reply reply;
    control_request(setup,configuration,&reply);
    send_reply(&reply);
    trace[0]=4;
}
static void receive_one(void) {
    uint32_t status=rd(RXPOP);
    trace[12]=status;
    unsigned ep=status&15, size=(status>>4)&0x7ff, kind=(status>>17)&15;
    if(kind==6 || kind==2) {
        if(size>64) fail(0x32);
        if(kind==6) setup_valid=(ep==0 && size==8);
        for(unsigned i=0;i<(size+3)/4;i++) {
            uint32_t word=rd(FIFO);
            if(kind==6 && setup_valid) for(unsigned j=0;j<4;j++) setup[4*i+j]=word>>(8*j);
        }
    } else if(kind==4 && ep==0) {
        wr(OUTINT,BIT(3)|BIT(15));
        dispatch_setup();
    } else if(kind==3 && ep==0) {
        wr(OUTINT,BIT(0));
        arm_out();
    }
}
__attribute__((section(".text.entry"),noreturn)) void usb_enum_main(void) {
    /* Assembly established MMU-off execution, framebuffer, gates and PHY. */
    if(rd(0x40)!=0x4f54272a || (rd(0x4c)>>16)<192) fail(1);
    /* PIO only, no IRQ delivery, no DMA addresses. */
    wr(GAHB,0); wr(GMSK,0);
    wr(DCTL,rd(DCTL)|BIT(1));
    wr(GUSB,(rd(GUSB)&~BIT(29))|BIT(30));
    if(!delay(2400000) || !wait_bits(GINT,BIT(0),0)) fail(2);
    wr(DCFG,0); /* high-speed capable, address0, descriptor DMA off */
    reset_ep0();
    wr(GINT,0xffffffff);
    wr(GMSK,BIT(4)|BIT(12)|BIT(13)|BIT(18)|BIT(19));
    wr(DCTL,rd(DCTL)|BIT(11));
    if(!delay(240)) fail(3);
    wr(DCTL,rd(DCTL)&~BIT(11));
    if(!delay(240000)) fail(4);
    trace[0]=1;
#ifdef USB_LINK_STATE
    link_dctl[0]=rd(DCTL);
#endif
#ifdef USB_PHY_ATTACH_GATE
    /* n42 iBEC16b94 calls15d34 before clearing DCTL.SFTDISCON.
     * That helper sets UVLDCON bit1 when PHY startup has completed.
     * Require our measured baseline4; preserve all other bits.
     */
    volatile uint32_t *uvld=(volatile uint32_t *)0x3600001c;
    attach_uvld[0]=*uvld;
    if(attach_uvld[0]!=4) fail(0x40);
    *uvld=attach_uvld[0]|BIT(1);
    barrier();
    attach_uvld[1]=*uvld;
    if(attach_uvld[1]!=6) fail(0x41);
#endif
    wr(DCTL,(rd(DCTL)&~BIT(1))|BIT(8)|BIT(10));
#ifdef USB_LINK_STATE
    link_dctl[1]=rd(DCTL);
#endif
    for(;;) {
        uint32_t intr=rd(GINT); trace[9]=intr; trace[10]=rd(DSTS);
        if(intr&BIT(12)) {
#ifdef USB_LINK_STATE
            if(!trace[1]) link_dctl[2]=rd(DCTL);
#endif
            trace[1]++; trace[0]=2;
            reset_ep0(); wr(GINT,BIT(12));
#ifdef USB_LINK_STATE
            if(trace[1]==1) link_dctl[3]=rd(DCTL);
#endif
            continue;
        }
        if(intr&BIT(13)) {
            trace[2]++; trace[0]=3;
            wr(INCTL,ACTIVE|BIT(27)); arm_out();
            wr(DCTL,rd(DCTL)|BIT(8)|BIT(10));
            wr(GINT,BIT(13));
        }
        /* Finish old IN status before dispatching a possible next SETUP. */
        uint32_t in=rd(ININT);
        if(in&BIT(0)) {
            wr(ININT,BIT(0)); trace[6]++;
            if(pending_address>=0) {
                wr(DCFG,(rd(DCFG)&~(127u<<4))|((uint32_t)pending_address<<4));
                trace[7]=pending_address; pending_address=-1;
            }
            if(pending_config>=0) {
                configuration=pending_config; trace[8]=configuration;
                pending_config=-1; trace[0]=5;
            }
        }
        if(in&BIT(3)) { wr(ININT,BIT(3)); trace[11]=0x33; }
        for(unsigned n=0;n<16 && (rd(GINT)&BIT(4));n++) receive_one();
        draw_line();
    }
}
/* Freestanding compiler support, no host library linked. */
void *memcpy(void *dst,const void *src,size_t n) {
    uint8_t *d=dst; const uint8_t *s=src; for(size_t i=0;i<n;i++) d[i]=s[i]; return dst;
}
void *memset(void *dst,int v,size_t n) {
    uint8_t *d=dst; for(size_t i=0;i<n;i++) d[i]=(uint8_t)v; return dst;
}

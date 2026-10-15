/* SPDX-License-Identifier: MIT
 * Bounded read-only Apple boot memory-map capture. Runs before Linux handoff.
 * boot_args ARM32 layout: Apple XNU pexpert/pexpert/arm/boot.h.
 * Apple tree layout: Brandon Azad's public-domain devicetree-parse.
 * Scratch [83fff100,83fffc00); stack [83fffc00,84000000).
 */
typedef unsigned int u32;
typedef unsigned char u8;
#define WORDS (0xb00 / 4)
#if defined(A6_CAPTURE_AUDIO) && (!defined(A6_CAPTURE_CLOCK) || defined(A6_CAPTURE_TOUCH))
#error Audio capture requires clock capture and excludes touch capture
#endif
#if defined(A6_CAPTURE_CPU_CLOCK) && !defined(A6_CAPTURE_CLOCK)
#error CPU fixed-clock capture requires clock capture
#endif
#if defined(A6_CAPTURE_TOUCH) && defined(A6_CAPTURE_CLOCK)
#error Choose calibration or clock capture, not both
#endif
#if defined(A6_CAPTURE_TOUCH) || defined(A6_CAPTURE_CLOCK)
#define MAX_RECORDS 19
#else
#define MAX_RECORDS 36
#endif
static u32 get32(const u8 *p)
{
    return (u32)p[0] | (u32)p[1]<<8 | (u32)p[2]<<16 | (u32)p[3]<<24;
}
#ifdef A6_CAPTURE_TOUCH
#include "capture-touch.inc"
#endif
#ifdef A6_CAPTURE_CLOCK
#include "capture-clock.inc"
#endif
#ifdef A6_CAPTURE_AUDIO
#include "capture-audio.inc"
#endif
static int name_is(const u8 *p, int map)
{
    if (p[0]!='m'||p[1]!='e'||p[2]!='m'||p[3]!='o'||p[4]!='r'||p[5]!='y') return 0;
    if (!map) return p[6]==0;
    return p[6]=='-'&&p[7]=='m'&&p[8]=='a'&&p[9]=='p'&&p[10]==0;
}
/* Returns 1 complete, 2 malformed/truncated, 3 depth/node limit exceeded.
 * Output header words5/6/7: record count, node count, truncation flags.
 * Records at byte128: kind,length,name[32],data[32] (72 bytes).
 */
int a6_parse_memory(const u8 *tree, u32 length, volatile u32 *out)
{
    u32 children[32], depth=0, pos=0, nodes=0;
#ifdef A6_CAPTURE_CPU_CLOCK
    u32 cpus_parent=0;
#endif
    children[0]=1;
    for (;;) {
        if (!children[depth]) { if (!depth) break; --depth; continue; }
        --children[depth];
        if (++nodes>4096) return 3;
        out[6]=nodes;
        if (pos>length || length-pos<8) return 2;
        u32 count=get32(tree+pos), child=get32(tree+pos+4), start, end, kind=0;
        pos+=8; start=pos;
#ifdef A6_CAPTURE_TOUCH
        u32 is_touch=0, is_n41=0;
        out[25]=3;
#endif
#ifdef A6_CAPTURE_CLOCK
        u32 is_armio=0;
        out[25]=4;
#endif
#ifdef A6_CAPTURE_CPU_CLOCK
        u32 is_cpu0=0, name_count=0;
        out[25]=5;
        if(depth==1)cpus_parent=0;
#endif
        if (count>4096 || child>4096) return 3;
        for (u32 i=0;i<count;++i) {
            if (pos>length || length-pos<36 || tree[pos+31]) return 2;
            u32 size=get32(tree+pos+32)&0x7fffffff;
            if (size>length-pos-36) return 2;
            if (tree[pos]=='n'&&tree[pos+1]=='a'&&tree[pos+2]=='m'&&tree[pos+3]=='e'&&!tree[pos+4]) {
#ifdef A6_CAPTURE_CPU_CLOCK
                ++name_count;
                if(depth==1 && size==5 && get32(tree+pos+36)==0x73757063 && !tree[pos+40]) {
                    cpus_parent=1;
                    ++out[0x780/4+5];
                }
                if(depth==2 && cpus_parent && size==5 &&
                   get32(tree+pos+36)==0x30757063 && !tree[pos+40])is_cpu0=1;
#endif
                #ifdef A6_CAPTURE_TOUCH
                if(size>=12 && touch_name(tree+pos+36))is_touch=1;
#endif
                #ifdef A6_CAPTURE_CLOCK
                if(depth==1 && size==7 && get32(tree+pos+36)==0x2d6d7261 &&
                   tree[pos+40]=='i' && tree[pos+41]=='o' && !tree[pos+42])is_armio=1;
#endif
                if (size>=7 && name_is(tree+pos+36,0)) kind=1;
                if (size>=11 && name_is(tree+pos+36,1)) kind=2;
            }
#ifdef A6_CAPTURE_TOUCH
            if(get32(tree+pos)==0x706d6f63 && get32(tree+pos+4)==0x62697461 &&
               tree[pos+8]=='l' && tree[pos+9]=='e' && !tree[pos+10] &&
               touch_compatible(tree+pos+36,size))is_n41=1;
#endif
            pos+=36+((size+3)&~3U);
            if (pos>length) return 2;
        }
        end=pos;
#ifdef A6_CAPTURE_AUDIO
        if(audio_control_node(tree,start,count))capture_audio_properties(tree,start,count,out);
#endif
#ifdef A6_CAPTURE_TOUCH
        if(is_touch && is_n41)capture_touch_properties(tree,start,count,out);
#endif
#ifdef A6_CAPTURE_CLOCK
        if(is_armio)capture_clock_properties(tree,start,count,out);
#endif
#ifdef A6_CAPTURE_CPU_CLOCK
        if((is_cpu0 || (depth==1 && cpus_parent)) && name_count!=1)
            out[0x780/4]|=16;
        if(is_cpu0)capture_cpu_clock_properties(tree,start,count,out);
#endif
        if (kind) for (u32 i=0, p=start;i<count;++i) {
            u32 size=get32(tree+p+32)&0x7fffffff;
            if (kind==2 || (tree[p]=='r'&&tree[p+1]=='e'&&tree[p+2]=='g'&&!tree[p+3])) {
                u32 n=out[5];
                if (n==MAX_RECORDS) out[7]|=1;
                else {
                    volatile u32 *rec=out+32+n*18;
                    rec[0]=kind;rec[1]=size;
                    for(u32 j=0;j<8;++j)rec[2+j]=get32(tree+p+j*4);
                    volatile u8 *value=(volatile u8 *)(rec+10);
                    for(u32 j=0;j<size && j<32;++j)value[j]=tree[p+36+j];
                    if(size>32)out[7]|=2;
                    out[5]=n+1;
                }
            }
            p+=36+((size+3)&~3U);
        }
        pos=end;
        if(child) {
            if(depth==31)return 3;
            children[++depth]=child;
        }
    }
    if(pos!=length)return 2;
    return 1;
}
/* Validate only the captured ARM32 prefix, never a complete v17 ABI.
 * Revision1/version17 observed on n42 iBEC: display fields independently
 * match the live framebuffer. Retain all RAM/tree bounds before traversal.
 */
int a6_memory_metadata(const u8 *a, volatile u32 *out)
{
    u32 revision=(u32)a[0]|(u32)a[1]<<8, version=(u32)a[2]|(u32)a[3]<<8;
    if (!((version>=1 && version<=2 && revision>=1 && revision<=2) ||
          (version==17 && revision==1))) return 11;
    u32 virt=get32(a+4),phys=get32(a+8),mem=get32(a+12),dt=get32(a+48),len=get32(a+52);
    out[3]=dt;out[4]=len;
    if(phys!=0x80000000U || mem<0x08000000U || mem>0x40000000U || len<8 || len>0x40000U)return 12;
    /* Translate only the declared linear RAM mapping, without guessing. */
    if(dt<virt || dt-virt>=mem || len>mem-(dt-virt))return 12;
    out[3]=phys+(dt-virt);
    return 0;
}
#ifndef A6_CAPTURE_TEST
/* Require currently mapped identity RAM pages, not arbitrary MMIO or aliases.
 * ATS1CPR is read-only address translation under ARMv7 VMSA; it changes PAR.
 */
static int readable(u32 base,u32 size,u32 sctlr,volatile u32 *out)
{
    if(base<0x80000000U || base>=0xc0000000U || !size || size>0xc0000000U-base)return 0;
    if(base<0x84000000U && base+size>0x83fff000U)return 0;
    /* With translation disabled, bounded physical RAM needs no AT lookup. */
    if (!(sctlr & 1)) return 1;
    u32 last=(base+size-1)&~4095U;
    for(u32 page=base&~4095U;;page+=4096) {
        u32 par;
        __asm__ volatile("mcr p15,0,%1,c7,c8,0\n\tisb\n\tmrc p15,0,%0,c7,c4,0" : "=r"(par) : "r"(page) : "memory");
        out[23]=par;out[24]=page;
        if((par&1) || (par&0xfffff000U)!=page)return 0;
        if(page==last)break;
    }
    return 1;
}
void a6_capture_memory(u32 args)
{
    /* Never clear a buffer overlapping the arguments we must preserve. */
    if (args >= 0x83ffefc8U && args < 0x84000000U) return;
    volatile u32 *out=(volatile u32 *)0x83fff100U;
    for(u32 i=0;i<WORDS;++i)out[i]=0;
    out[0]=0x41364d31U;out[1]=10;out[2]=args;
    u32 sctlr;
    __asm__ volatile("mrc p15,0,%0,c1,c0,0":"=r"(sctlr));
    out[22]=sctlr;out[25]=2;
    if(!readable(args,56,sctlr,out))return;
    const u8 *a=(const u8 *)args;
    for(u32 i=0;i<14;++i)out[8+i]=get32(a+i*4);
    u32 status=a6_memory_metadata(a,out);
    if(status) {out[1]=status;return;}
    u32 dt=out[3],len=out[4];out[1]=13;
    if(!readable(dt,len,sctlr,out))return;
    out[1]=a6_parse_memory((const u8 *)dt,len,out);
}
#endif

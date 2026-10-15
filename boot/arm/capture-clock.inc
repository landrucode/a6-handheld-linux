/* Read-only live arm-io clock table; exclusive with calibration capture.
 * Header26 flags(1 present,4 length/duplicate,8 duplicate node),27 nodes,
 * 28 bytes,29 nonzero bytes. Full384-byte table at600..77f.
 */
static void capture_clock_properties(const u8 *tree, u32 start, u32 count,
                                      volatile u32 *out)
{
    if (++out[27]!=1) {out[26]|=8;return;}
    for(u32 i=0,p=start;i<count;++i) {
        u32 size=get32(tree+p+32)&0x7fffffff;
        if(get32(tree+p)==0x636f6c63 && get32(tree+p+4)==0x72662d6b &&
           get32(tree+p+8)==0x65757165 && get32(tree+p+12)==0x6569636e &&
           tree[p+16]=='s' && !tree[p+17]) {
            if(size!=384 || (out[26]&1))out[26]|=4;
            else {
                volatile u8 *dest=(volatile u8 *)out+0x600;
                out[26]|=1;out[28]=size;
                for(u32 j=0;j<size;++j) {dest[j]=tree[p+36+j];out[29]+=(dest[j]!=0);}
            }
        }
        p+=36+((size+3)&~3U);
    }
}
#ifdef A6_CAPTURE_CPU_CLOCK
/* Revision5 extension at780: flags,CPU0 nodes,size,low,high,cpus nodes.
 * Exact /cpus/cpu0 only; require running state before using the frequency.
 */
static void capture_cpu_clock_properties(const u8 *tree, u32 start, u32 count,
                                         volatile u32 *out)
{
    volatile u32 *cpu=out+0x780/4;
    if(++cpu[1]!=1) {cpu[0]|=8;return;}
    u32 states=0;
    for(u32 i=0,p=start;i<count;++i) {
        u32 size=get32(tree+p+32)&0x7fffffff;
        if(get32(tree+p)==0x65786966 && get32(tree+p+4)==0x72662d64 &&
           get32(tree+p+8)==0x65757165 && get32(tree+p+12)==0x0079636e) {
            if((size!=4 && size!=8) || (cpu[0]&1))cpu[0]|=4;
            else {
                cpu[0]|=1;cpu[2]=size;
                cpu[3]=get32(tree+p+36);
                if(size==8)cpu[4]=get32(tree+p+40);
            }
        }
        if(get32(tree+p)==0x74617473 && tree[p+4]=='e' && !tree[p+5]) {
            if(++states!=1)cpu[0]|=16;
            if(size==8 && get32(tree+p+36)==0x6e6e7572 &&
               get32(tree+p+40)==0x00676e69)cpu[0]|=2;
        }
        p+=36+((size+3)&~3U);
    }
}
#endif

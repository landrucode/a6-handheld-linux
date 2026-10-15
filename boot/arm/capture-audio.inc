/* SPDX-License-Identifier: MIT
 * Owner-only pre-Linux audio calibration capture. No syscfg/NAND access.
 * Header+0x800, config+0x820, SRdc+0x840, optional calib+0x850 (256 max).
 * Capture populated firmware-tree bytes, never treat references as data.
 */
static int audio_control_node(const u8 *tree,u32 start,u32 count)
{
    for(u32 i=0,p=start;i<count;++i) {
        u32 size=get32(tree+p+32)&0x7fffffff;
        if((get32(tree+p)==0x706d6f63 && get32(tree+p+4)==0x62697461 && tree[p+8]=='l' && tree[p+9]=='e' && !tree[p+10]) && size==22 &&
           (get32(tree+p+36)==0x69647561 && get32(tree+p+40)==0x6f632d6f && get32(tree+p+44)==0x6f72746e && get32(tree+p+48)==0x73632c6c && get32(tree+p+52)==0x316c3533 && tree[p+56]=='9' && !tree[p+57]))return 1;
        p+=36+((size+3)&~3U);
    }
    return 0;
}
static void capture_audio_properties(const u8 *tree,u32 start,u32 count,volatile u32 *out)
{
    volatile u32 *h=out+0x800/4;
    u32 seen=0;
    h[0]=0x53504431;
    if(++h[2]!=1){h[1]|=32;return;}
    for(u32 i=0,p=start;i<count;++i) {
        u32 size=get32(tree+p+32)&0x7fffffff,bit=0,offset=0,index=0;
        if(get32(tree+p)==0x61657073 && get32(tree+p+4)==0x2d72656b && get32(tree+p+8)==0x666e6f63 && tree[p+12]=='i' && tree[p+13]=='g' && !tree[p+14]){bit=1;offset=0x820;index=3;}
        if(get32(tree+p)==0x61657073 && get32(tree+p+4)==0x2d72656b && tree[p+8]=='r' && tree[p+9]=='d' && tree[p+10]=='c' && !tree[p+11]){bit=2;offset=0x840;index=4;}
        if(get32(tree+p)==0x61657073 && get32(tree+p+4)==0x2d72656b && get32(tree+p+8)==0x696c6163 && tree[p+12]=='b' && !tree[p+13]){bit=4;offset=0x850;index=5;}
        if(bit) {
            if(seen&bit)h[1]|=16;
            else if(size>=7 && get32(tree+p+36)==0x63737973 && tree[p+40]=='f' && tree[p+41]=='g' && tree[p+42]=='/')h[1]|=8;
            else if((bit==1 && size!=20)||(bit==2 && size!=4)||(bit==4 && (!size||size>256)))h[1]|=16;
            else {
                volatile u8 *dest=(volatile u8 *)out+offset;
                for(u32 j=0;j<size;++j)dest[j]=tree[p+36+j];
                h[index]=size;h[1]|=bit;
            }
        }
        seen|=bit;
        p+=36+((size+3)&~3U);
    }
}

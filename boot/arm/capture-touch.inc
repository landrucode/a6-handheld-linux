/* Read-only n41 calibration extension. Header words26..31, payload0x600.
 * Only enabled in a separate diagnostic image. Memory records capped at19
 * (end0x5d8); calibration1024+128 bytes ends0xa80, below0xb00/stack boundary.
 * Flags:1 touch present,2 prox present,4 bad length/duplicate property,
 * 8 duplicate matching node. Zero-filled calibration is captured, not trusted.
 */
static int touch_name(const u8 *p)
{
    return get32(p)==0x746c756d && get32(p+4)==0x6f742d69 && get32(p+8)==0x00686375;
}
static int touch_compatible(const u8 *p, u32 size)
{
    return size>=16 && get32(p)==0x746c756d && get32(p+4)==0x6f742d69 &&
           get32(p+8)==0x2c686375 && get32(p+12)==0x0031346e;
}
static void capture_touch_properties(const u8 *tree, u32 start, u32 count,
                                     volatile u32 *out)
{
    if (++out[27]!=1) {out[26]|=8;return;}
    for (u32 i=0,p=start;i<count;++i) {
        u32 size=get32(tree+p+32)&0x7fffffff, kind=0;
        if(get32(tree+p)==0x746c756d && get32(tree+p+4)==0x6f742d69 &&
           get32(tree+p+8)==0x2d686375 && get32(tree+p+12)==0x696c6163 &&
           get32(tree+p+16)==0x74617262 && get32(tree+p+20)==0x006e6f69)kind=1;
        if(get32(tree+p)==0x786f7270 && get32(tree+p+4)==0x6c61632d &&
           get32(tree+p+8)==0x61726269 && get32(tree+p+12)==0x6e6f6974 &&
           tree[p+16]==0)kind=2;
        if(kind) {
            u32 expected=kind==1?1024:128, index=kind==1?28:29;
            if(size!=expected || (out[26]&kind))out[26]|=4;
            else {
                volatile u8 *dest=(volatile u8 *)out+(kind==1?0x600:0xa00);
                out[index]=size;out[26]|=kind;
                for(u32 j=0;j<size;++j) {dest[j]=tree[p+36+j];out[index+2]+=(dest[j]!=0);}
            }
        }
        p+=36+((size+3)&~3U);
    }
}

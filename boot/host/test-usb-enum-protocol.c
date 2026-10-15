#include <assert.h>
#include <stdio.h>
#include "../arm/usb-enum-protocol.h"
int main(void)
{
    struct control_reply r;
    uint8_t s[8]={0x80,6,0,1,0,0,64,0};
    control_request(s,0,&r);
    assert(r.action==REPLY_DATA && r.length==18 && r.data[7]==64);
    assert(le16(r.data+8)==0x1209 && le16(r.data+10)==1);
    s[6]=8; control_request(s,0,&r); assert(r.length==8);
    s[6]=255; s[7]=255; control_request(s,0,&r); assert(r.length==18);
    s[3]=2; control_request(s,0,&r);
    assert(r.length==18 && le16(r.data+2)==18 && r.data[13]==0);
    s[3]=7; control_request(s,0,&r); assert(r.data[1]==7);
    s[3]=6; control_request(s,0,&r); assert(r.length==10);
    s[3]=3; control_request(s,0,&r); assert(r.action==REPLY_STALL);
    uint8_t address[8]={0,5,127,0,0,0,0,0};
    control_request(address,0,&r); assert(r.action==REPLY_ADDRESS && r.value==127);
    address[2]=128; control_request(address,0,&r); assert(r.action==REPLY_STALL);
    uint8_t config[8]={0,9,1,0,0,0,0,0};
    control_request(config,0,&r); assert(r.action==REPLY_CONFIG && r.value==1);
    config[2]=2; control_request(config,0,&r); assert(r.action==REPLY_STALL);
    /* All bmRequestType/request combinations, with hostile maximum fields. */
    for (unsigned type=0;type<256;type++) for(unsigned req=0;req<256;req++) {
        uint8_t bad[8]={type,req,255,255,255,255,255,255};
        control_request(bad,0,&r); assert(r.action==REPLY_STALL);
    }
    puts("USB descriptor/request tests passed (including 65536 malformed requests)");
}

/* Private enumeration diagnostic only. 1209:0001 is pid.codes' non-unique
 * in-house test PID; never redistribute devices using this identity.
 * https://pid.codes/1209/0001/
 */
#ifndef A6_USB_ENUM_PROTOCOL_H
#define A6_USB_ENUM_PROTOCOL_H
#include <stdint.h>

enum reply_action { REPLY_STALL, REPLY_DATA, REPLY_ADDRESS, REPLY_CONFIG };
struct control_reply {
    enum reply_action action;
    uint16_t length;
    uint8_t value;
    uint8_t data[64];
};
static const uint8_t device_descriptor[] = {
    18,1,0,2,0,0,0,64,0x09,0x12,1,0,0,1,0,0,0,1
};
static const uint8_t config_descriptor[] = {
    9,2,18,0,1,1,0,0x80,50, 9,4,0,0,0,0xff,0,0,0
};
static const uint8_t qualifier_descriptor[] = {10,6,0,2,0,0,0,64,1,0};
static uint16_t le16(const uint8_t *p) { return p[0] | ((uint16_t)p[1]<<8); }
static void control_request(const uint8_t s[8], uint8_t configured,
                            struct control_reply *r)
{
    uint16_t value=le16(s+2), index=le16(s+4), length=le16(s+6);
    const uint8_t *p=0;
    unsigned n=0;
    r->action=REPLY_STALL; r->length=0; r->value=0;
    if (s[0]==0x80 && s[1]==6 && !index && !(value & 255)) {
        switch (value>>8) {
        case 1: p=device_descriptor; n=sizeof(device_descriptor); break;
        case 2: case 7: p=config_descriptor; n=sizeof(config_descriptor); break;
        case 6: p=qualifier_descriptor; n=sizeof(qualifier_descriptor); break;
        default: return;
        }
        if (n>length) n=length;
        for (unsigned i=0;i<n;i++) r->data[i]=p[i];
        if ((value>>8)==7 && n>1) r->data[1]=7;
        r->length=n; r->action=REPLY_DATA;
    } else if (s[0]==0 && s[1]==5 && value<128 && !index && !length) {
        r->action=REPLY_ADDRESS; r->value=value;
    } else if (s[0]==0 && s[1]==9 && value<=1 && !index && !length) {
        r->action=REPLY_CONFIG; r->value=value;
    } else if (s[0]==0x80 && s[1]==8 && !value && !index && length==1) {
        r->action=REPLY_DATA; r->length=1; r->data[0]=configured;
    } else if (s[1]==0 && !value && length==2 &&
               ((s[0]==0x80 && !index) ||
                (s[0]==0x81 && !index && configured) ||
                (s[0]==0x82 && (index==0 || index==0x80)))) {
        r->action=REPLY_DATA; r->length=2; r->data[0]=0; r->data[1]=0;
    } else if (s[0]==0x81 && s[1]==10 && !value && !index &&
               length==1 && configured) {
        r->action=REPLY_DATA; r->length=1; r->data[0]=0;
    } else if (s[0]==1 && s[1]==11 && !value && !index &&
               !length && configured) {
        r->action=REPLY_DATA;
    }
}
#endif

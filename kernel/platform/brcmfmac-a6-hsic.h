/* SPDX-License-Identifier: ISC */
/* N42 stock-confirmed HSIC framing. No device access or firmware commands. */
#ifndef BRCMFMAC_A6_HSIC_H
#define BRCMFMAC_A6_HSIC_H

static inline unsigned int brcmf_a6_hsic_word(const u8 *p)
{
	return p[0] | ((unsigned int)p[1] << 8);
}

/* Return bytes to remove; negative means malformed or wrong-direction header.
 * Headerless packets still undergo the normal BCDC parser afterwards.
 */
static inline int brcmf_a6_hsic_rx_offset(const u8 *p, unsigned int length)
{
	unsigned int flags, sum = 0, i;

	if (length < 2 || length > 65535)
		return -EMSGSIZE;
	flags = brcmf_a6_hsic_word(p);
	if (!(flags & 0x8000))
		return 0;
	if (length < 16 || brcmf_a6_hsic_word(p + 4) != length)
		return -EMSGSIZE;
	if (flags & 0x7000)
		return -EPROTO;
	for (i = 0; i < 16; i += 2)
		sum += brcmf_a6_hsic_word(p + i);
	sum = (sum & 0xffff) + (sum >> 16);
	sum = (sum & 0xffff) + (sum >> 16);
	return sum == 0xffff ? 16 : -EPROTO;
}

/* Stock startBulkWrite: kind2/flags a001, zero reserved words, total length
 * at4, incrementing sequence at6 and one's-complement header checksum at2.
 * Host-tested builder only: not yet enabled in the upstream transport.
 */
static inline int brcmf_a6_hsic_tx_header(u8 *header, unsigned int payload,
				       u16 sequence)
{
	unsigned int length, sum, i;

	if (!payload || payload > 65535 - 16)
		return -EMSGSIZE;
	length = payload + 16;
	for (i = 0; i < 16; i++)
		header[i] = 0;
	header[0] = 1;
	header[1] = 0xa0;
	header[4] = length & 255;
	header[5] = length >> 8;
	header[6] = sequence & 255;
	header[7] = sequence >> 8;
	sum = 0xa001 + length + sequence;
	sum = (sum & 0xffff) + (sum >> 16);
	sum = (sum & 0xffff) + (sum >> 16);
	sum = (~sum) & 0xffff;
	header[2] = sum & 255;
	header[3] = sum >> 8;
	return 0;
}
#endif

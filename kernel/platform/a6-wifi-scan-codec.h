/* SPDX-License-Identifier: GPL-2.0-only */
/* Offline-tested escan v1 / BSS109 ABI. No hardware or firmware commands.
 * Not included by the running trial. Callers retain raw bytes privately.
 */
#ifndef A6_WIFI_SCAN_CODEC_H
#define A6_WIFI_SCAN_CODEC_H
static unsigned int a6_scan_le(const unsigned char *p, unsigned int n)
{
    unsigned int v = 0, i;
    for (i = 0; i < n; i++) v |= (unsigned int)p[i] << (i * 8);
    return v;
}
static void a6_scan_put(unsigned char *p, unsigned int v, unsigned int n)
{
    unsigned int i;
    for (i = 0; i < n; i++) p[i] = v >> (i * 8);
}
/* Explicit already-encoded chanspecs; no implicit all-channel scan or SSIDs.
 * One passive start request, or abort action with the same sync token.
 * Passive 120ms dwell, no probes; enforcement/transmission remains firmware.
 */
static int a6_scan_request(unsigned char *p, unsigned int capacity,
        const unsigned short *channels, unsigned int count,
        unsigned short sync, unsigned int abort)
{
    unsigned int i, size;
    if (!p || !sync || abort > 1 || (!abort && (!channels || !count || count > 13)))
        return -EINVAL;
    if (!abort) for (i = 0; i < count; i++)
        if (!channels[i] || channels[i] == 65535) return -EINVAL;
    size = abort ? 72 : 72 + ((count * 2 + 3) & ~3U);
    if (capacity < size) return -EMSGSIZE;
    for (i = 0; i < size; i++) p[i] = 0;
    a6_scan_put(p, 1, 4); a6_scan_put(p + 4, abort ? 3 : 1, 2);
    a6_scan_put(p + 6, sync, 2);
    for (i = 44; i < 50; i++) p[i] = 255; /* broadcast BSSID */
    p[50] = 2; p[51] = 1; /* any BSS, passive */
    a6_scan_put(p + 52, 0, 4); /* nprobes */
    a6_scan_put(p + 56, ~0U, 4); /* unused active dwell */
    a6_scan_put(p + 60, 120, 4); a6_scan_put(p + 64, ~0U, 4);
    a6_scan_put(p + 68, abort ? 0 : count, 4);
    if (!abort) for (i = 0; i < count; i++) a6_scan_put(p + 72 + i * 2, channels[i], 2);
    return size;
}
/* PARTIAL event69 body: one BSS109; return1 only after all lengths and IEs
 * validate. Outer envelope/event status are a separate caller gate.
 * N42 measured escan result version109 / BSS109. Unknown ABI returns EOPNOTSUPP; wrong sync is stale.
 */
static int a6_scan_partial(const unsigned char *p, unsigned int bytes,
                          unsigned short sync)
{
    unsigned int total, record, ie, n, i;
    const unsigned char *bss;
    if (!p || bytes < 140 || bytes > 2048) return -EMSGSIZE;
    total = a6_scan_le(p, 4);
    if (total < 140 || total > bytes || total > 2048) return -EMSGSIZE;
    if (a6_scan_le(p + 4, 4) != 109) return -EOPNOTSUPP;
    if (a6_scan_le(p + 8, 2) != sync || !sync) return -ESTALE;
    if (a6_scan_le(p + 10, 2) != 1) return -EPROTO;
    bss = p + 12;
    if (a6_scan_le(bss, 4) != 109) return -EOPNOTSUPP;
    record = a6_scan_le(bss + 4, 4);
    if (record != total - 12 || record < 128) return -EMSGSIZE;
    if (bss[18] > 32 || a6_scan_le(bss + 52, 4) > 16) return -EPROTO;
    ie = a6_scan_le(bss + 116, 2); n = a6_scan_le(bss + 120, 4);
    if (ie < 128 || ie > record || n > record - ie) return -EMSGSIZE;
    for (i = 0; i < n;) {
        unsigned int size;
        if (n - i < 2) return -EMSGSIZE;
        size = bss[ie + i + 1];
        if (size > n - i - 2) return -EMSGSIZE;
        i += 2 + size;
    }
    return 1;
}
#endif

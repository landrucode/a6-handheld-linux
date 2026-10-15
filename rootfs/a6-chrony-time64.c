/* SPDX-License-Identifier: MIT
 * Private ARM32 chronyd runtime adapter for mixed time_t package ABIs.
 * Chrony 4.9 supplies a signed 32-bit cooked-time callback; the installed
 * GnuTLS expects signed 64-bit time. Preserve that clock and validation.
 * Remove when chronyd is rebuilt consistently with _TIME_BITS=64.
 */
#include <stdint.h>
#include <dlfcn.h>
#include <unistd.h>

typedef int32_t (*clock32_fn)(int32_t *);
typedef int64_t (*clock64_fn)(int64_t *);
static clock32_fn cooked_clock;

static int64_t cooked_time64(int64_t *result)
{
    int64_t now = cooked_clock(0);
    if (result)
        *result = now;
    return now;
}

void gnutls_global_set_time_function(clock32_fn function)
{
    void (*set_time64)(clock64_fn) =
        (void (*)(clock64_fn))dlsym(RTLD_NEXT, "gnutls_global_set_time_function");
    if (!set_time64 || !function)
        _exit(127);
    cooked_clock = function;
    set_time64(cooked_time64);
}

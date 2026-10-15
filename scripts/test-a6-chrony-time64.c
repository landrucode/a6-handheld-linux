/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdint.h>

static int64_t (*installed)(int64_t *);
static void install(int64_t (*function)(int64_t *)) { installed = function; }
static void *test_dlsym(void *handle, const char *name)
{
    (void)handle;
    (void)name;
    return (void *)install;
}
#define dlsym test_dlsym
#include "../rootfs/a6-chrony-time64.c"
#undef dlsym

static int32_t value;
static int32_t callback(int32_t *result)
{
    assert(result == 0);
    return value;
}

int main(void)
{
    int32_t cases[] = {0, 1791498473, INT32_MAX, -1, INT32_MIN};
    gnutls_global_set_time_function(callback);
    for (unsigned int i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        value = cases[i];
        int64_t result = INT64_C(0x7777777777777777);
        assert(installed(0) == (int64_t)value);
        assert(installed(&result) == (int64_t)value);
        assert(result == (int64_t)value);
    }
    return 0;
}

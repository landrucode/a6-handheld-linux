#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <libirecovery.h>

#include "libbootkit/boot.h"
#include "libbootkit/protocol.h"

#define ARM_RESET_VECTOR 0xEA00000E

static void usage(const char *program) {
    fprintf(stderr, "Usage: %s probe | prepare <unpacked-ibss> | boot <unpacked-ibss>\n", program);
}

static int read_file(const char *path, uint8_t **data, size_t *length) {
    FILE *file = fopen(path, "rb");
    if (!file) {
        fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
        return -1;
    }

    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return -1;
    }

    long end = ftell(file);
    if (end <= 0) {
        fclose(file);
        fprintf(stderr, "bootloader is empty or unreadable\n");
        return -1;
    }

    rewind(file);
    uint8_t *buffer = malloc((size_t)end);
    if (!buffer) {
        fclose(file);
        fprintf(stderr, "unable to allocate %ld bytes\n", end);
        return -1;
    }

    size_t got = fread(buffer, 1, (size_t)end, file);
    fclose(file);
    if (got != (size_t)end) {
        free(buffer);
        fprintf(stderr, "short read from %s\n", path);
        return -1;
    }

    *data = buffer;
    *length = got;
    return 0;
}

static int open_pwned_device(irecv_client_t *client) {
    irecv_error_t error = irecv_open_with_ecid(client, 0);
    if (error != IRECV_E_SUCCESS) {
        fprintf(stderr, "cannot open DFU device: %s\n", irecv_strerror(error));
        return -1;
    }

    if (validate_device(*client) != 0) {
        irecv_close(*client);
        *client = NULL;
        return -1;
    }

    return 0;
}

static int probe_device(void) {
    irecv_client_t client = NULL;
    if (open_pwned_device(&client) != 0) {
        return -1;
    }

    const struct irecv_device_info *info = irecv_get_device_info(client);
    printf("CPID: 0x%04x\n", info->cpid);
    printf("BDID: 0x%02x\n", info->bdid);
    printf("ECID: 0x%016" PRIx64 "\n", info->ecid);
    printf("SRTG: %s\n", info->srtg ? info->srtg : "N/A");
    printf("SERIAL: %s\n", info->serial_string ? info->serial_string : "N/A");

    irecv_close(client);
    return 0;
}

static int run_boot(const char *verb, const char *path) {
    uint8_t *bootloader = NULL;
    size_t bootloader_length = 0;
    if (read_file(path, &bootloader, &bootloader_length) != 0) {
        return -1;
    }

    if (bootloader_length < sizeof(uint32_t)) {
        fprintf(stderr, "bootloader is too small\n");
        free(bootloader);
        return -1;
    }

    uint32_t reset_vector = 0;
    memcpy(&reset_vector, bootloader, sizeof(reset_vector));
    if (reset_vector != ARM_RESET_VECTOR) {
        fprintf(stderr, "bootloader does not start with ARM reset vector 0x%08x\n", ARM_RESET_VECTOR);
        free(bootloader);
        return -1;
    }

    irecv_client_t client = NULL;
    if (open_pwned_device(&client) != 0) {
        free(bootloader);
        return -1;
    }

    bool prepare_only = strcmp(verb, "prepare") == 0;
    int result = dfu_boot(client, bootloader, bootloader_length, prepare_only);
    if (result == 0) {
        if (prepare_only) {
            printf("command prepared locally; no device write was requested\n");
        } else {
            printf("boot command submitted; device USB state may change\n");
        }
    }

    irecv_close(client);
    free(bootloader);
    return result;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "probe") == 0) {
        return probe_device() == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
    }

    if (argc == 3 && (strcmp(argv[1], "prepare") == 0 || strcmp(argv[1], "boot") == 0)) {
        return run_boot(argv[1], argv[2]) == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
    }

    usage(argv[0]);
    return EXIT_FAILURE;
}

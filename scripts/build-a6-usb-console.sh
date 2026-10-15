#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export A6_USB_CONSOLE=1
if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then export A6_MEMORY_CAPTURE=1; fi
if [[ "${A6_MEMORY_CAPTURE:-0}" == 1 ]]; then export A6_WAYLAND_LOCKS=1; fi
if [[ "${A6_WAYLAND_LOCKS:-0}" == 1 ]]; then export A6_XORG_CREDENTIALS=1; fi
if [[ "${A6_XORG_CREDENTIALS:-0}" == 1 ]]; then export A6_FB_PLATFORM=1; fi
if [[ "${A6_FB_PLATFORM:-0}" == 1 ]]; then export A6_FRAMEBUFFER=1; fi
if [[ "${A6_FRAMEBUFFER:-0}" == 1 ]]; then export A6_ARCH_USERSPACE=1; fi
if [[ "${A6_ARCH_USERSPACE:-0}" == 1 ]]; then export A6_VFP=1; fi
if [[ "${A6_VFP:-0}" == 1 ]]; then export A6_USB_NETWORK=1; fi
if [[ "${A6_USB_NETWORK:-0}" == 1 ]]; then export A6_QUIET_SHELL=1; fi
if [[ "${A6_QUIET_SHELL:-0}" == 1 ]]; then export A6_LOCAL_FULL_TLBI=1; fi
if [[ "${A6_LOCAL_FULL_TLBI:-0}" == 1 ]]; then export A6_ROLLOVER_TLBI=1; fi
if [[ "${A6_ROLLOVER_TLBI:-0}" == 1 ]]; then export A6_LOCAL_RANGE_TLBI=1; fi
if [[ "${A6_LOCAL_RANGE_TLBI:-0}" == 1 ]]; then export A6_LOCAL_ASID_TLBI=1; fi
if [[ "${A6_LOCAL_ASID_TLBI:-0}" == 1 ]]; then export A6_LOCAL_PAGE_TLBI=1; fi
if [[ "${A6_LOCAL_PAGE_TLBI:-0}" == 1 ]]; then
    [[ "${A6_SHELL_TLBI_PROOF:-0}" == 0 ]]
    export A6_SHELL_PTE_TRACE=1
fi
if [[ "${A6_SHELL_TLBI_PROOF:-0}" == 1 ]]; then export A6_SHELL_PTE_TRACE=1; fi
if [[ "${A6_SHELL_PTE_TRACE:-0}" == 1 ]]; then export A6_SHELL_FAULT_TRACE=1; fi
if [[ "${A6_SHELL_FAULT_TRACE:-0}" == 1 ]]; then export A6_SHELL_EXEC_TRACE=1; fi
if [[ "${A6_SHELL_EXEC_TRACE:-0}" == 1 ]]; then export A6_USB_SHELL=1; fi
if [[ "${A6_USB_SHELL:-0}" == 1 ]]; then export A6_EXEC_PREP_TRACE=1; fi
if [[ "${A6_EXEC_PREP_TRACE:-0}" == 1 ]]; then export A6_EXEC_TRACE=1; fi
if [[ "${A6_EXEC_TRACE:-0}" == 1 ]]; then export A6_USB_WAIT_TRACE=1; fi
if [[ "${A6_USB_WAIT_TRACE:-0}" == 1 ]]; then export A6_USB_SYNC_TRACE=1; fi
if [[ "${A6_USB_SYNC_TRACE:-0}" == 1 ]]; then export A6_USB_REQUEST_TRACE=1; fi
if [[ "${A6_USB_REQUEST_TRACE:-0}" == 1 ]]; then export A6_TIMER_A2=1; fi
if [[ "${A6_TIMER_A2:-0}" == 1 ]]; then
    [[ "${A6_TIMER_LINE_TRACE:-0}" == 0 && "${A6_AIC_ROUTE_TRACE:-0}" == 0 ]]
    export A6_TIMER_TRACE=1
fi
if [[ "${A6_TIMER_LINE_TRACE:-0}" == 1 ]]; then export A6_TIMER_TRACE=1; fi
if [[ "${A6_AIC_ROUTE_TRACE:-0}" == 1 ]]; then export A6_TIMER_TRACE=1; fi
if [[ "${A6_TIMER_TRACE:-0}" == 1 ]]; then export A6_USB_PHY_TRACE=1; fi
if [[ "${A6_USB_PHY_TRACE:-0}" == 1 ]]; then export A6_USB_BOOT_STATUS=1; fi
kind=usb-console
if [[ "${A6_USB_BOOT_STATUS:-0}" == 1 ]]; then kind=usb-status; fi
if [[ "${A6_USB_PHY_TRACE:-0}" == 1 ]]; then kind=usb-phy-trace; fi
if [[ "${A6_TIMER_TRACE:-0}" == 1 ]]; then kind=usb-timer-trace; fi
if [[ "${A6_AIC_ROUTE_TRACE:-0}" == 1 ]]; then kind=usb-aic-route; fi
if [[ "${A6_TIMER_LINE_TRACE:-0}" == 1 ]]; then kind=usb-timer-line; fi
if [[ "${A6_TIMER_A2:-0}" == 1 ]]; then kind=usb-timer-a2; fi
if [[ "${A6_USB_REQUEST_TRACE:-0}" == 1 ]]; then kind=usb-request-trace; fi
if [[ "${A6_USB_SYNC_TRACE:-0}" == 1 ]]; then kind=usb-sync-trace; fi
if [[ "${A6_USB_WAIT_TRACE:-0}" == 1 ]]; then kind=usb-wait-trace; fi
if [[ "${A6_EXEC_TRACE:-0}" == 1 ]]; then kind=usb-exec-trace; fi
if [[ "${A6_EXEC_PREP_TRACE:-0}" == 1 ]]; then kind=usb-exec-prep; fi
if [[ "${A6_USB_SHELL:-0}" == 1 ]]; then kind=usb-shell; fi
if [[ "${A6_SHELL_EXEC_TRACE:-0}" == 1 ]]; then kind=usb-shell-exec; fi
if [[ "${A6_SHELL_FAULT_TRACE:-0}" == 1 ]]; then kind=usb-shell-fault; fi
if [[ "${A6_SHELL_PTE_TRACE:-0}" == 1 ]]; then kind=usb-shell-pte; fi
if [[ "${A6_SHELL_TLBI_PROOF:-0}" == 1 ]]; then kind=usb-shell-tlbi; fi
if [[ "${A6_LOCAL_PAGE_TLBI:-0}" == 1 ]]; then kind=usb-shell-page-tlbi; fi
if [[ "${A6_LOCAL_ASID_TLBI:-0}" == 1 ]]; then kind=usb-shell-asid-tlbi; fi
if [[ "${A6_LOCAL_RANGE_TLBI:-0}" == 1 ]]; then kind=usb-shell-range-tlbi; fi
if [[ "${A6_ROLLOVER_TLBI:-0}" == 1 ]]; then kind=usb-shell-rollover-tlbi; fi
if [[ "${A6_LOCAL_FULL_TLBI:-0}" == 1 ]]; then kind=usb-shell-full-tlbi; fi
if [[ "${A6_QUIET_SHELL:-0}" == 1 ]]; then
    kind=usb-shell-quiet
    # Platform dependencies above remain selected; only repeated diagnostic
    # generation is disabled. Keep EXEC_TRACE for permanent-text relocation.
    export A6_EXEC_PREP_TRACE=0 A6_SHELL_EXEC_TRACE=0
    export A6_SHELL_FAULT_TRACE=0 A6_SHELL_PTE_TRACE=0
fi
if [[ "${A6_USB_NETWORK:-0}" == 1 ]]; then kind=usb-network; fi
if [[ "${A6_VFP:-0}" == 1 ]]; then kind=usb-network-vfp; fi
if [[ "${A6_ARCH_USERSPACE:-0}" == 1 ]]; then kind=arch-userspace; fi
if [[ "${A6_FRAMEBUFFER:-0}" == 1 ]]; then kind=arch-framebuffer; fi
if [[ "${A6_FB_PLATFORM:-0}" == 1 ]]; then kind=arch-fb-platform; fi
if [[ "${A6_XORG_CREDENTIALS:-0}" == 1 ]]; then kind=arch-xorg-credentials; fi
if [[ "${A6_WAYLAND_LOCKS:-0}" == 1 ]]; then kind=arch-wayland-locks; fi
if [[ "${A6_MEMORY_CAPTURE:-0}" == 1 ]]; then kind=arch-memory-capture; fi
if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then kind=arch-direct-drm; fi
if [[ "${A6_BATTERY_OBSERVER:-0}" == 1 ]]; then
    [[ "${A6_DIRECT_DRM:-0}" == 1 ]]
    kind=battery-observer
fi
if [[ "${A6_BATTERY_HDQ_READ:-0}" == 1 ]]; then
    [[ "${A6_DIRECT_DRM:-0}" == 1 && "${A6_BATTERY_OBSERVER:-0}" == 0 ]]
    kind=battery-hdq-read
    if [[ "${A6_HDQ_LINE_OBSERVER:-0}" == 1 ]]; then
        kind=battery-hdq-line-observer
    fi
fi
if [[ "${A6_TOUCH_TRANSPORT:-0}" == 1 ]]; then
    [[ "${A6_DIRECT_DRM:-0}" == 1 && ( "${A6_CAPTURE_TOUCH:-0}" == 1 || "${A6_CAPTURE_CLOCK:-0}" == 1 ) ]]
    kind=touch-transport
    if [[ "${A6_TOUCH_CLOCK:-0}" == 1 ]]; then
        [[ "${A6_CAPTURE_CLOCK:-0}" == 1 && ( "${A6_TOUCH_CHECK:-0}" == 0 || "${A6_TOUCH_PWM_CHECK:-0}" == 1 ) ]]
        kind=touch-clock
    fi
    if [[ "${A6_TOUCH_I2C:-0}" == 1 ]]; then
        [[ ( "${A6_TOUCH_CHECK:-0}" == 0 && "${A6_TOUCH_CLOCK:-0}" == 0 ) || "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]
        kind=touch-i2c
        if [[ "${A6_TOUCH_PMU_READ:-0}" == 1 ]]; then kind=touch-pmu-read; fi
    fi
    if [[ "${A6_TOUCH_CHECK:-0}" == 1 ]]; then
        kind=${A6_TOUCH_CHECK_KIND:-touch-check}
        [[ "$kind" == touch-check || "$kind" == touch-check-start || "$kind" == touch-pwm-check || "$kind" == touch-pwm-readback || "$kind" == touch-pwm-steady || "$kind" == touch-power-check || "$kind" == touch-gpio-cs || "$kind" == touch-hbpp || "$kind" == touch-n1-version || "$kind" == touch-n1-start-version || "$kind" == charger-proof ]]
        if [[ "$kind" == touch-pwm-check || "$kind" == touch-pwm-readback || "$kind" == touch-pwm-steady || "$kind" == touch-power-check || "$kind" == touch-gpio-cs || "$kind" == touch-hbpp || "$kind" == touch-n1-version || "$kind" == touch-n1-start-version || "$kind" == charger-proof ]]; then
            [[ "${A6_TOUCH_PWM_CHECK:-0}" == 1 && "${A6_TOUCH_CLOCK:-0}" == 1 && "${A6_CAPTURE_CPU_CLOCK:-0}" == 1 ]]
        else
            [[ "${A6_TOUCH_PWM_CHECK:-0}" == 0 ]]
        fi
    fi
    if [[ "${A6_TOUCH_POWER_CHECK:-0}" == 1 ]]; then
        [[ ( "$kind" == touch-power-check || "$kind" == touch-gpio-cs || "$kind" == touch-hbpp || "$kind" == touch-n1-version || "$kind" == touch-n1-start-version || "$kind" == charger-proof ) && "${A6_TOUCH_I2C:-0}" == 1 && "${A6_TOUCH_PMU_READ:-0}" == 0 ]]
    fi
fi
[[ "${A6_TIMER_LINE_TRACE:-0}${A6_AIC_ROUTE_TRACE:-0}" != 11 ]]
if [[ "${A6_USB_BUS_POWERED:-0}" == 1 ]]; then
    [[ "$kind" == charger-proof && "${A6_USB_NETWORK:-0}" == 1 ]]
    kind=charger-usb-power
    if [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]; then
        kind=charger-vbus-adc
    fi
    if [[ "${A6_D1972_VBAT_ADC:-0}" == 1 ]]; then
        [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]
        kind=charger-vbat-adc
    fi
    if [[ "${A6_D1972_VBAT_MONITOR:-0}" == 1 ]]; then
        [[ "${A6_D1972_VBAT_ADC:-0}" == 1 ]]
        kind=charger-vbat-monitor
    fi
    if [[ "${A6_D1972_TBAT_ADC:-0}" == 1 ]]; then
        [[ "$kind" == charger-vbat-monitor ]]
        kind=charger-tbat-adc
    fi
    if [[ "${A6_D1972_POLICY:-0}" == 1 ]]; then
        [[ "$kind" == charger-tbat-adc ]]
        kind=charger-policy-500
        if [[ "${A6_D1972_STOCK_OFF_CANDIDATE:-0}" == 1 ]]; then
            kind=stock-off-candidate
            if [[ "${A6_D1972_LOW_BATTERY_CANDIDATE:-0}" == 1 ]]; then
                kind=low-battery-candidate
                if [[ "${A6_USB_VBUS_BRIDGE:-0}" == 1 ]]; then
                    kind=low-battery-vbus-bridge
                    if [[ "${A6_USB_BVALID_OVERRIDE:-0}" == 1 ]]; then
                        kind=low-battery-bvalid
                    fi
                    if [[ "${A6_DWC2_FULL_SPEED_ONLY:-0}" == 1 ]]; then
                        kind=low-battery-vbus-full-speed
                    fi
                fi
                if [[ "${A6_LOW_BATTERY_TRACE_SCREEN:-0}" == 1 ]]; then
                    kind=low-battery-trace
                fi
            fi
        fi
    fi
fi
if [[ "${A6_POWER_HDQ_PHASE:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor && "${A6_BATTERY_HDQ_READ:-0}" == 1 && "${A6_HDQ_LINE_OBSERVER:-0}" == 1 && "${A6_HDQ_PHASE_OBSERVER:-0}" == 1 ]]
    kind=charger-vbat-hdq-phase
fi
if [[ "${A6_POWER_HDQ_TIMED:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor && "${A6_BATTERY_HDQ_READ:-0}" == 1 && "${A6_HDQ_LINE_OBSERVER:-0}" == 1 && "${A6_HDQ_PHASE_OBSERVER:-0}" == 1 && "${A6_HDQ_REALTIME_US:-0}" == 1 ]]
    kind=charger-vbat-hdq-timed
fi
if [[ "${A6_POWER_HDQ_ECHO_GUARD:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor && "${A6_BATTERY_HDQ_READ:-0}" == 1 && "${A6_HDQ_LINE_OBSERVER:-0}" == 1 && "${A6_HDQ_PHASE_OBSERVER:-0}" == 1 && "${A6_HDQ_REALTIME_US:-0}" == 1 && "${A6_HDQ_ECHO_GUARD:-0}" == 1 ]]
    kind=charger-vbat-hdq-echo-guard
fi
if [[ "${A6_POWER_HDQ_TX_TURNAROUND:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-hdq-echo-guard && "${A6_HDQ_TX_TURNAROUND:-0}" == 1 ]]
    kind=charger-vbat-hdq-tx-turnaround
fi
if [[ "${A6_POWER_BACKLIGHT_TRIAL:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor && "${A6_BACKLIGHT_TRIAL:-0}" == 1 ]]
    kind=charger-vbat-backlight-trial
fi
power_kind="$kind"
if [[ "${A6_TOUCH_FW_UPLOAD:-0}" == 1 ]]; then
    [[ ( "$kind" == charger-vbat-hdq-echo-guard ||
        ( "$kind" == low-battery-vbus-bridge && "${A6_TOUCH_RAM_ROOT_CANDIDATE:-0}" == 1 ) ) &&
        "${A6_TOUCH_HBPP:-0}" == 1 && "${A6_TOUCH_GPIO_CS:-0}" == 1 ]]
    kind=touch-fw-n42
fi
if [[ "${A6_TOUCH_POST_UPLOAD:-0}" == 1 ]]; then
    [[ "$kind" == touch-fw-n42 ]]
    kind=touch-post-n42
fi
if [[ "${A6_TOUCH_REPORT_PROBE:-0}" == 1 ]]; then
    [[ "$kind" == touch-post-n42 ]]
    kind=touch-report-n42
fi
if [[ "${A6_TOUCH_CALIBRATION:-0}" == 1 ]]; then
    [[ "$kind" == touch-report-n42 && "${A6_TOUCH_CORRECT_EXEC_ADDR:-0}" == 1 ]]
    kind=touch-full-n42
fi
if [[ "${A6_TOUCH_E2_RETRY:-0}" == 1 ]]; then
    [[ "$kind" == touch-full-n42 ]]
    kind=touch-retry-n42
fi
if [[ "${A6_TOUCH_CLK32_ENABLE:-0}" == 1 ]]; then
    [[ "$kind" == touch-retry-n42 ]]
    kind=touch-clk32-n42
fi
if [[ "${A6_TOUCH_E3_INFO:-0}" == 1 ]]; then
    [[ "$kind" == touch-clk32-n42 ]]
    kind=touch-e3-info-n42
fi
if [[ "${A6_CHARGER_ACTIVE_TRIAL:-0}" == 1 ]]; then
    [[ "$kind" == touch-clk32-n42 && "${A6_CHARGER_PROOF:-0}" == 1 && "${A6_USB_BUS_POWERED:-0}" == 1 ]]
    kind=touch-charge-trial-n42
fi
if [[ "${A6_TOUCH_RAM_ROOT_CANDIDATE:-0}" == 1 ]]; then
    [[ "$kind" == touch-e3-info-n42 && "$power_kind" == low-battery-vbus-bridge ]]
    kind="$power_kind"
fi
if [[ "${A6_USB_RECONNECT_SCREEN:-0}" == 1 ]]; then
    if [[ "${A6_USB_WALL_SCREEN:-0}" == 1 ]]; then
        [[ "${A6_DIRECT_DRM:-0}" == 1 && ( "$kind" == low-battery-vbus-bridge || "$kind" == low-battery-bvalid ) ]]
        [[ "${A6_USB_RECONNECT_PHY:-0}" == 1 && "${A6_USB_RECONNECT_VBUS_LATCH:-0}" == 1 ]]
        [[ "${A6_USB_RECONNECT_LX_LATCH:-0}" == 0 && "${A6_USB_RECONNECT_EP0:-0}" == 0 ]]
        if [[ "${A6_USB_CORE_RESET_TRACE:-0}" == 1 ]]; then
            [[ "$kind" == low-battery-vbus-bridge ]]
            if [[ "${A6_USB_CORE_STAGE_TRACE:-0}" == 1 ]]; then
                kind=low-battery-reset-stage
                if [[ "${A6_USB_VBUS_AUTO_RECOVER:-0}" == 1 ]]; then
                    kind=low-battery-auto-recover
                    if [[ "${A6_D1972_BOOT_DEFAULTS:-0}" == 1 ]]; then
                        kind=low-battery-boot-defaults
                    fi
                fi
            else
                kind=low-battery-reset-trace
            fi
        elif [[ "$kind" == low-battery-bvalid ]]; then
            kind=low-battery-bvalid-screen
        else
            kind=low-battery-vbus-screen
        fi
    else
        [[ "${A6_DIRECT_DRM:-0}" == 1 && "$kind" == charger-policy-500 ]]
        kind=usb-reconnect-screen
        if [[ "${A6_USB_RECONNECT_PHY:-0}" == 1 ]]; then
            kind=usb-reconnect-phy
            if [[ "${A6_USB_RECONNECT_VBUS_LATCH:-0}" == 1 ]]; then
                kind=usb-reconnect-vbus-latch
            fi
            if [[ "${A6_USB_RECONNECT_LX_LATCH:-0}" == 1 ]]; then
                kind=usb-reconnect-lx-latch
                if [[ "${A6_USB_RECONNECT_REARM:-0}" == 1 ]]; then
                    kind=usb-reconnect-lx-rearm
                fi
                if [[ "${A6_USB_RECONNECT_L3_REARM:-0}" == 1 ]]; then
                    [[ "${A6_USB_RECONNECT_REARM:-0}" != 1 ]]
                    kind=usb-reconnect-l3-rearm
                fi
            fi
            if [[ "${A6_USB_RECONNECT_ENUM_REARM:-0}" == 1 ]]; then
                kind=usb-reconnect-enum-rearm
            fi
        fi
        if [[ "${A6_USB_RECONNECT_EP0:-0}" == 1 ]]; then
            kind=usb-reconnect-ep0
            if [[ "${A6_USB_RECONNECT_REARM:-0}" == 1 ]]; then
                kind=usb-reconnect-rearm
            fi
        fi
    fi
fi
if [[ "${A6_TOUCH_RAM_ROOT_CANDIDATE:-0}" == 1 ]]; then
    [[ "${A6_TOUCH_E3_INFO:-0}" == 1 && "${A6_RAM_ROOT:-0}" == 1 &&
       "${A6_D1972_BOOT_DEFAULTS:-0}" == 1 && "${A6_SMP_SCHEDULING:-0}" == 1 ]]
    kind="$kind-touch-ram-root"
    if [[ "${A6_TOUCH_FRAME_CAPTURE:-0}" == 1 ]]; then kind="$kind-frames"; fi
    if [[ "${A6_TOUCH_NATIVE_INPUT:-0}" == 1 ]]; then kind="$kind-native"; fi
fi
if [[ "${A6_WIFI_CLOCK_SNAPSHOT:-0}" == 1 ]]; then
    [[ "${A6_FRAMEBUFFER:-0}" == 1 && "${A6_TOUCH_RAM_ROOT_CANDIDATE:-0}" == 1 ]]
    if [[ "${A6_WIFI_EHCI_ENUM:-0}" == 1 ]]; then
        python3 "$repo_root/scripts/verify-a6-wifi-clock-dispatch.py" >/dev/null
        python3 "$repo_root/scripts/verify-a6-wifi-ready-dispatch.py" >/dev/null
        kind="$kind-wifi-ehci-enum"
    elif [[ "${A6_WIFI_EHCI_CAPS:-0}" == 1 ]]; then
        python3 "$repo_root/scripts/verify-a6-wifi-clock-dispatch.py" >/dev/null
        kind="$kind-wifi-ehci-caps"
    else
        kind="$kind-wifi-clock-snapshot"
    fi
fi
if [[ "${A6_SMP_COMPILE_ONLY:-0}" == 1 ]]; then
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
        kind="$kind-smp-cpu0-only"
    elif [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        if [[ "${A6_SMP_SCHEDULING:-0}" == 1 ]]; then
            kind="$kind-smp-first-scheduling"
        else
            if [[ "${A6_SMP_TIMER_LINE_PROBE:-0}" == 1 ]]; then
                kind="$kind-smp-timer-line-checkpoint"
            else
                kind="$kind-smp-bridge-quarantine"
            fi
        fi
    else
        kind="$kind-smp-compile-only"
    fi
fi
if [[ "${A6_CPU1_PREFLIGHT:-0}" == 1 ]]; then
    [[ "${A6_SMP_COMPILE_ONLY:-0}" != 1 ]]
    if [[ "${A6_CPU1_ALIAS_PREFLIGHT:-0}" == 1 ]]; then
        if [[ "${A6_CPU1_CACHE_SHAREABLE_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-cache-shareable-probe"
        elif [[ "${A6_CPU1_CACHE_REPEAT_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-cache-repeat-probe"
        elif [[ "${A6_CPU1_CACHE_TRE_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-cache-tre-probe"
        elif [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-cache-probe"
        elif [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-tlbi-probe"
        elif [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-ipi-probe"
            if [[ "${A6_CPU1_IPI_CHECKPOINTS:-0}" == 1 ]]; then
                kind="$kind-checkpoints"
            fi
        elif [[ "${A6_CPU1_ENTRY_PROBE:-0}" == 1 ]]; then
            kind="$kind-cpu1-entry-probe"
        elif [[ "${A6_CPU1_ALIAS_WRITE:-0}" == 1 ]]; then
            kind="$kind-cpu1-alias-write-proof"
        else
            kind="$kind-cpu1-alias-preflight"
        fi
    else
        kind="$kind-cpu1-preflight-v2"
    fi
fi
export A6_OUTPUT_ROOT="$repo_root/build/linux-a6-$kind"
export A6_DTB_OUTPUT="$repo_root/build/arm/a6-n42ap-$kind.dtb"
export A6_COMBINED_OUTPUT="$repo_root/build/arm/a6-n42ap-$kind-zImage-with-dtb"
bash "$repo_root/scripts/build-a6-zimage.sh"
# Eight identity sections cover 80000000..807fffff; Image starts80008000.
image_size="$(stat -c %s "$A6_OUTPUT_ROOT/arch/arm/boot/Image")"
(( image_size > 0 && image_size <= 0x800000 - 0x8000 ))
if [[ "${A6_USB_BOOT_STATUS:-0}" == 1 ]]; then
	python3 "$repo_root/scripts/verify-a6-boot-status.py" "$A6_OUTPUT_ROOT"
fi
if [[ "${A6_TIMER_A2:-0}" == 1 ]]; then
    timer_verify_args=()
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
        timer_verify_args+=(--smp-cpu0-only)
    elif [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        timer_verify_args+=(--smp-bridge-quarantine)
    elif [[ "${A6_CPU1_ALIAS_PREFLIGHT:-0}" == 1 ]]; then
        if [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]; then
            timer_verify_args+=(--cpu1-tlbi-reservations)
        else
            timer_verify_args+=(--cpu1-reservations)
        fi
    fi
    if [[ "${A6_DWC2_FULL_SPEED_ONLY:-0}" == 1 ]]; then
        timer_verify_args+=(--full-speed)
    fi
    python3 "$repo_root/scripts/verify-a6-timer-a2.py" \
        "$A6_OUTPUT_ROOT" "$A6_DTB_OUTPUT" "${timer_verify_args[@]}"
fi
gadget_option=USB_G_SERIAL
if [[ "${A6_USB_NETWORK:-0}" == 1 ]]; then gadget_option=USB_CDC_COMPOSITE; fi
console_option=U_SERIAL_CONSOLE
if [[ "${A6_WIFI_NATIVE:-0}" == 1 ]]; then console_option=NULL_TTY; fi
for option in USB_DWC2 USB_DWC2_PERIPHERAL "$gadget_option" "$console_option" GENERIC_PHY DEVTMPFS BINFMT_ELF; do
	rg -q "^CONFIG_${option}=y$" "$A6_OUTPUT_ROOT/.config"
done
if [[ "${A6_ARCH_USERSPACE:-0}" == 1 ]]; then
    for option in VFP VFPv3 NEON UNIX EPOLL SIGNALFD TIMERFD EVENTFD INOTIFY_USER POSIX_TIMERS SYSVIPC TMPFS UNIX98_PTYS; do
        rg -q "^CONFIG_${option}=y$" "$A6_OUTPUT_ROOT/.config"
    done
fi
if [[ "${A6_FRAMEBUFFER:-0}" == 1 ]]; then
    for option in FB FB_CORE FB_A6_BOOT FB_IOMEM_FOPS; do
        rg -q "^CONFIG_${option}=y$" "$A6_OUTPUT_ROOT/.config"
    done
    rg -q '^# CONFIG_FRAMEBUFFER_CONSOLE is not set$' "$A6_OUTPUT_ROOT/.config"
fi
if [[ "${A6_XORG_CREDENTIALS:-0}" == 1 ]]; then
    rg -q "^CONFIG_MULTIUSER=y$" "$A6_OUTPUT_ROOT/.config"
fi
if [[ "${A6_WAYLAND_LOCKS:-0}" == 1 ]]; then
    rg -q "^CONFIG_FILE_LOCKING=y$" "$A6_OUTPUT_ROOT/.config"
fi
if [[ "${A6_DIRECT_DRM:-0}" == 1 ]]; then
    for option in DRM DRM_SIMPLEDRM KERNEL_XZ INPUT_EVDEV INPUT_UINPUT; do
        rg -q "^CONFIG_${option}=y$" "$A6_OUTPUT_ROOT/.config"
    done
    python3 - "$A6_DTB_OUTPUT" "${A6_TOUCH_TRANSPORT:-0}" "${A6_BATTERY_OBSERVER:-0}" "${A6_BATTERY_HDQ_READ:-0}" <<'RAM'
import os,struct,sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_bytes();old=struct.pack('>II',0x80000000,0x08000000)
assert s.count(old)==1
ram=0x30000000 if '1' in sys.argv[2:5] else 0x20000000
requested=os.environ.get('A6_RAM_MIB','768')
assert requested in ('768','944'), 'unsupported RAM diagnostic'
if requested=='944':
    assert os.environ.get('A6_BROWSER_SANDBOX')=='1' and ram==0x30000000
    ram=944*1024*1024
p.write_bytes(s.replace(old,struct.pack('>II',0x80000000,ram)))
print(f'PASS direct DRM {ram//1024//1024} MiB DT and preserved scratch reservation')
RAM
fi
export A6_ZIMAGE="$A6_OUTPUT_ROOT/arch/arm/boot/zImage"
export A6_DTB="$A6_DTB_OUTPUT"
export A6_PAYLOAD="$A6_COMBINED_OUTPUT"
export A6_KERNELCACHE_RAW="$repo_root/build/arm/a6-linux-$kind.raw"
export A6_KERNELCACHE_IMG3="$repo_root/build/arm/a6-linux-$kind.img3"
export A6_KERNELCACHE_ROUNDTRIP="$repo_root/build/arm/a6-linux-$kind.roundtrip.raw"
if [[ "${A6_SMP_COMPILE_ONLY:-0}" == 1 ]]; then
    rg -q '^CONFIG_SMP=y$' "$A6_OUTPUT_ROOT/.config"
    rg -q '^CONFIG_NR_CPUS=2$' "$A6_OUTPUT_ROOT/.config"
    if [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 ]]; then
        python3 "$repo_root/scripts/check-a6-smp-bridge.py" "$A6_OUTPUT_ROOT" "$A6_DTB"
    elif [[ "${A6_SMP_CPU0_ONLY:-0}" != 1 ]]; then
        echo "A6 SMP compile-only: no IMG3 packaging or hardware boot"
        exit 0
    fi
    if [[ "${A6_SMP_CPU0_ONLY:-0}" == 1 ]]; then
    rg -q '^CONFIG_CMDLINE="[^"]* maxcpus=1"$' "$A6_OUTPUT_ROOT/.config"
    rg -q '^CONFIG_CMDLINE_FORCE=y$' "$A6_OUTPUT_ROOT/.config"
    "$A6_OUTPUT_ROOT/scripts/dtc/dtc" -I dtb -O dts "$A6_DTB" 2>/dev/null |
        rg -q 'maxcpus=1'
    if "$A6_OUTPUT_ROOT/scripts/dtc/dtc" -I dtb -O dts "$A6_DTB" 2>/dev/null |
        rg -q 'cpu@1'; then
        echo 'refusing CPU0-only SMP image with CPU1 DT node' >&2
        exit 1
    fi
    fi
fi
bash "$repo_root/scripts/build-a6-kernelcache.sh"

#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export A6_USB_BUS_POWERED=1 A6_CHARGER_PROOF=1 A6_D1972_POWER_SUPPLY=1 A6_DIRECT_DRM=1
export A6_BUILD_JOBS=4
export A6_TOUCH_TRANSPORT=1 A6_CAPTURE_TOUCH=0 A6_CAPTURE_CLOCK=1 A6_CAPTURE_CPU_CLOCK=1
export A6_TOUCH_CLOCK=1 A6_TOUCH_I2C=1 A6_TOUCH_CHECK=1 A6_TOUCH_PWM_CHECK=1 A6_TOUCH_POWER_CHECK=1
export A6_TOUCH_CHECK_KIND=charger-proof
bash scripts/build-a6-usb-console.sh
if [[ "${A6_D1972_VBAT_MONITOR:-0}" == 1 ]]; then
    [[ "${A6_D1972_VBAT_ADC:-0}" == 1 && "${A6_D1972_VBUS_ADC:-0}" == 1 ]]
    kind=charger-vbat-monitor
    if [[ "${A6_D1972_TBAT_ADC:-0}" == 1 ]]; then
        kind=charger-tbat-adc
        if [[ "${A6_D1972_POLICY:-0}" == 1 ]]; then
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
                        if [[ "${A6_USB_WALL_SCREEN:-0}" == 1 ]]; then
                            [[ "${A6_DWC2_FULL_SPEED_ONLY:-0}" == 0 ]]
                            if [[ "${A6_USB_CORE_RESET_TRACE:-0}" == 1 ]]; then
                                [[ "${A6_USB_BVALID_OVERRIDE:-0}" == 0 ]]
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
                            elif [[ "${A6_USB_BVALID_OVERRIDE:-0}" == 1 ]]; then
                                kind=low-battery-bvalid-screen
                            else
                                kind=low-battery-vbus-screen
                            fi
                        fi
                    fi
                    if [[ "${A6_LOW_BATTERY_TRACE_SCREEN:-0}" == 1 ]]; then
                        kind=low-battery-trace
                    fi
                fi
            fi
            if [[ "${A6_USB_RECONNECT_SCREEN:-0}" == 1 && "${A6_USB_WALL_SCREEN:-0}" != 1 ]]; then
                kind=usb-reconnect-screen
                if [[ "${A6_USB_RECONNECT_PHY:-0}" == 1 ]]; then
                    kind=usb-reconnect-phy
                    if [[ "${A6_USB_RECONNECT_VBUS_LATCH:-0}" == 1 ]]; then
                        kind=usb-reconnect-vbus-latch
                    fi
                    if [[ "${A6_USB_RECONNECT_LX_LATCH:-0}" == 1 ]]; then
                        kind=usb-reconnect-lx-latch
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
    fi
elif [[ "${A6_D1972_VBAT_ADC:-0}" == 1 ]]; then
    [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]
    kind=charger-vbat-adc
elif [[ "${A6_D1972_VBUS_ADC:-0}" == 1 ]]; then
    kind=charger-vbus-adc
else
    kind=charger-usb-power
fi
if [[ "${A6_POWER_HDQ_PHASE:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor ]]
    kind=charger-vbat-hdq-phase
fi
if [[ "${A6_POWER_HDQ_TIMED:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor ]]
    kind=charger-vbat-hdq-timed
fi
if [[ "${A6_POWER_HDQ_ECHO_GUARD:-0}" == 1 ]]; then
    [[ "$kind" == charger-vbat-monitor ]]
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
rg -q '^CONFIG_USB_CDC_COMPOSITE=y$' "build/linux-a6-$kind/.config"
rg -q '^CONFIG_POWER_SUPPLY=y$' "build/linux-a6-$kind/.config"
python3 scripts/verify-a6-charger-usb-power.py "$kind"
sha256sum "build/arm/a6-linux-$kind.img3"

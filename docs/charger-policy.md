# Charger policy when monitoring stops

This note covers what the charger code does if the host stops receiving data
(see the discharge in [test-results.md](test-results.md#power-and-battery)).
It is based on reading the source, not on measurements.

## Where the policy runs

The charger policy runs as kernel delayed work (`a6_policy_tick()` calls
`a6_auto_step()`). The low-battery shutdown is a separate kernel worker. Both
keep running if USB or a userspace logger stops. They stop only if the kernel
or their worker hangs.

## What it sets

The policy asks the PMU for a 500 mA charge target with a 480 mA input limit
(`A6_POLICY_TARGET` and `A6_POLICY_INPUT`). These are requests. The actual
battery current depends on the load, the power source and the PMU.

To stop charging, `a6_policy_disable()` selects the PMU's lowest charge
setting (below 70 mA) and
clears the charge target. It also clears the input limit unless `keep_input`
is set. So an input limit that is still set does not mean charging is on.

The ten-minute lease for manual charging is checked in software. Automatic
charging does not use that lease, and the driver does not set up a separate
PMU charging watchdog.

## If the kernel hangs

If the kernel or the policy worker hangs, the code cannot stop charging or
shut the phone down. What the PMU then does on its own is unknown. Finding
out needs a hardware measurement; the last saved register values are not
enough.

Source: `kernel/platform/a6-d1972-policy.inc`.

# Pressure and recovery uncertainty extension

CleanroomX extends its deterministic conservative-interval method to room differential pressure, room-to-room pressure cascades, and measured particle-recovery qualification.

## Room pressure

A room may define:

    observed_pressure_pa
    observed_pressure_uncertainty_pa

The measurement interval is:

    observed pressure ± absolute uncertainty

For a configured minimum pressure requirement:

- **pass**: the complete pressure interval is at or above the minimum;
- **fail**: the complete pressure interval is below the minimum;
- **indeterminate**: the minimum lies inside the interval.

If no uncertainty is supplied, the default is zero and the historical nominal behavior is preserved.

## Pressure cascade

For two measured room pressures, CleanroomX uses conservative interval arithmetic.

For a nominal difference:

    delta_p = pressure_high - pressure_low

and absolute pressure uncertainties u_high and u_low:

    delta_p interval = delta_p ± (u_high + u_low)

This is deliberately a worst-case deterministic bound. It does not assume independence or combine uncertainties statistically.

## Particle recovery

Each recovery sample may optionally include:

    concentration_uncertainty_per_m3

For a target concentration, a sample is classified as:

- **at_or_below** when its complete concentration interval is at or below the target;
- **above** when its complete interval is above the target;
- **indeterminate** when the interval overlaps the target.

A maximum recovery-time criterion is passed only when a sample definitely demonstrates recovery within the configured time. If a sample interval overlaps the target within the allowed time but definite recovery is only demonstrated later, the result is **indeterminate** rather than a forced pass or fail.

The existing log-linear recovery diagnostic continues to use nominal concentration values only.

## Scope

These calculations propagate user-supplied absolute bounds. They do not derive instrument uncertainty, calibration uncertainty, confidence levels, probability distributions, or regulatory decision rules. Project qualification procedures, calibration records, applicable standards, and qualified engineering judgment remain authoritative for real projects.

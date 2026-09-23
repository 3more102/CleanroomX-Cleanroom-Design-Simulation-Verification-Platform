# Psychrometric state uncertainty workflow

CleanroomX v0.15 adds deterministic uncertainty envelopes for psychrometric air-state inputs and derived properties.

## Scope

The workflow accepts user-supplied nominal values and absolute uncertainty bounds for:

- dry-bulb temperature;
- relative humidity;
- total pressure.

It reports bounded values for:

- water-vapor partial pressure;
- humidity ratio;
- moist-air enthalpy;
- moist-air specific volume;
- dew-point temperature;
- moist-air specific heat at constant pressure.

No uncertainty magnitude is invented by CleanroomX.

## Method

The accepted input region is a rectangular interval box:

    T = T_nominal ± u_T
    RH = RH_nominal ± u_RH
    P = P_nominal ± u_P

CleanroomX evaluates every unique corner of that box with the same psychrometric equations used by the existing HVAC workflow. The nominal state is evaluated separately.

For the implemented equations over the supported input domain, increasing dry-bulb temperature and relative humidity increases vapor pressure and humidity ratio, while increasing total pressure reduces humidity ratio. The remaining reported derived properties follow those same bounded inputs. Evaluating the complete corner set therefore provides a transparent deterministic envelope without assuming a probability distribution.

## Input validation

The complete uncertainty box must remain inside the implemented psychrometric domain:

- dry-bulb temperature: -45 to 60 °C;
- relative humidity: greater than 0% and no more than 100%;
- total pressure: greater than 0 kPa;
- the maximum permitted water-vapor partial pressure must remain below the minimum total pressure.

## Traceability

Each uncertain input can carry the standard CleanroomX provenance record: source type/name, reference, revision, date, uncertainty basis, and notes. Missing provenance is reported separately from the calculated intervals.

## Engineering boundary

This is deterministic interval screening. It is not a statistical measurement-uncertainty budget and does not model covariance, probability distributions, sensor drift, calibration corrections, spatial gradients, or transient air conditions.

The workflow does not create project acceptance limits. Use calibrated instruments, project qualification procedures, applicable standards, and qualified engineering judgment for real measurements and design decisions.

The standalone v0.15 workflow remains available for direct air-state envelope analysis. The thermal-uncertainty workflow can also accept uncertain room/outdoor dry-bulb temperature, relative humidity, and pressure and propagate those corner states into makeup-air load and sensible-load airflow. See `docs/THERMAL_UNCERTAINTY.md` for the coupled screening model.

## CLI

    cleanroomx-psychrometric-uncertainty examples/psychrometric_uncertainty_demo.json

JSON output:

    cleanroomx-psychrometric-uncertainty examples/psychrometric_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-psychrometric-uncertainty examples/psychrometric_uncertainty_demo.json --output psychrometric-uncertainty-report.md

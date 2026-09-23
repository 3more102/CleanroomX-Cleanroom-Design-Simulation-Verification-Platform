from __future__ import annotations


def _validate_inputs(
    value: float,
    uncertainty_abs: float | None,
    uncertainty_percent: float | None,
) -> tuple[float, float | None, float | None]:
    value = float(value)
    absolute = None if uncertainty_abs is None else float(uncertainty_abs)
    percent = None if uncertainty_percent is None else float(uncertainty_percent)

    if absolute is not None and percent is not None:
        raise ValueError(
            "provide either absolute uncertainty or percentage uncertainty, not both"
        )
    if absolute is not None and absolute < 0:
        raise ValueError("absolute uncertainty must be >= 0")
    if percent is not None and percent < 0:
        raise ValueError("percentage uncertainty must be >= 0")
    return value, absolute, percent


def measurement_interval(
    value: float,
    *,
    uncertainty_abs: float | None = None,
    uncertainty_percent: float | None = None,
    floor: float | None = None,
) -> dict:
    value, absolute, percent = _validate_inputs(
        value, uncertainty_abs, uncertainty_percent
    )

    if absolute is None and percent is None:
        return {
            "available": False,
            "value": value,
            "uncertainty_abs": None,
            "uncertainty_percent": None,
            "lower_bound": None,
            "upper_bound": None,
        }

    uncertainty = absolute if absolute is not None else abs(value) * percent / 100.0
    lower = value - uncertainty
    upper = value + uncertainty
    if floor is not None:
        lower = max(float(floor), lower)

    return {
        "available": True,
        "value": value,
        "uncertainty_abs": uncertainty,
        "uncertainty_percent": percent,
        "lower_bound": lower,
        "upper_bound": upper,
    }


def upper_limit_decision(
    value: float,
    limit: float,
    *,
    uncertainty_abs: float | None = None,
    uncertainty_percent: float | None = None,
    floor: float | None = None,
) -> dict:
    limit = float(limit)
    interval = measurement_interval(
        value,
        uncertainty_abs=uncertainty_abs,
        uncertainty_percent=uncertainty_percent,
        floor=floor,
    )
    if not interval["available"]:
        return {
            **interval,
            "limit": limit,
            "status": "not_available",
            "message": "No measurement uncertainty was supplied.",
        }

    if interval["upper_bound"] <= limit:
        status = "pass"
        message = "The full measurement interval is at or below the configured limit."
    elif interval["lower_bound"] > limit:
        status = "fail"
        message = "The full measurement interval is above the configured limit."
    else:
        status = "indeterminate"
        message = "The measurement interval overlaps the configured limit."

    return {
        **interval,
        "limit": limit,
        "status": status,
        "message": message,
    }

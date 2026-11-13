from __future__ import annotations

from backend.core.errors import ApiError
from backend.modules.chronos.schemas import CalendarConfiguration, CalendarDate


def _leap_days_before_year(configuration: CalendarConfiguration, year: int) -> int:
    """Count intercalary days in calendar years [0, year), including negative years."""
    total = 0
    for rule in configuration.leap_rules:
        # Number of integers n in [0, year) for which n ≡ offset (mod period).
        total += (
            (year - 1 - rule.year_offset) // rule.every_years
            - (-1 - rule.year_offset) // rule.every_years
        ) * rule.extra_days
    return total


def _month_days(
    configuration: CalendarConfiguration, year: int, month: int
) -> int:
    days = configuration.months[month - 1].days
    for rule in configuration.leap_rules:
        if month == rule.month and (year - rule.year_offset) % rule.every_years == 0:
            days += rule.extra_days
    return days


def date_window(
    configuration: CalendarConfiguration,
    date: CalendarDate,
    precision: str,
) -> tuple[int, int]:
    """Convert a custom-calendar date into an inclusive sortable day window."""
    months = configuration.months
    year_length = sum(month.days for month in months)
    year_start = (
        date.year * year_length
        + _leap_days_before_year(configuration, date.year)
        + configuration.epoch_offset
    )
    this_year_length = year_length + sum(
        rule.extra_days
        for rule in configuration.leap_rules
        if (date.year - rule.year_offset) % rule.every_years == 0
    )

    if precision == "year":
        if date.month is not None or date.day is not None:
            raise ApiError(422, "invalid_calendar_date", "Year-precision dates must contain only a year.")
        return year_start, year_start + this_year_length - 1

    if date.month is None:
        raise ApiError(422, "invalid_calendar_date", "A month is required for this date precision.")
    if date.month > len(months):
        raise ApiError(422, "invalid_calendar_date", "The month is not defined by this calendar.")

    month_start = year_start + sum(
        _month_days(configuration, date.year, month_number)
        for month_number in range(1, date.month)
    )
    month_days = _month_days(configuration, date.year, date.month)
    if precision == "month":
        if date.day is not None:
            raise ApiError(422, "invalid_calendar_date", "Month-precision dates must not include a day.")
        return month_start, month_start + month_days - 1

    if date.day is None or date.day > month_days:
        raise ApiError(422, "invalid_calendar_date", "The day is not defined for this month.")
    exact_day = month_start + date.day - 1
    return exact_day, exact_day


def event_day_window(
    configuration: CalendarConfiguration,
    *,
    start_date: CalendarDate,
    end_date: CalendarDate | None,
    precision: str,
    uncertainty: dict[str, int] | None,
) -> tuple[int, int]:
    if precision == "approximate":
        if end_date is not None:
            raise ApiError(422, "invalid_date_precision", "Approximate dates use uncertainty instead of an end date.")
        center_start, center_end = date_window(configuration, start_date, "day")
        if center_start != center_end:
            raise ApiError(422, "invalid_calendar_date", "Approximate dates must identify an exact central day.")
        values = uncertainty or {}
        before = values.get("before_days", 0)
        after = values.get("after_days", 0)
        return center_start - before, center_end + after

    if precision == "range":
        if end_date is None:
            raise ApiError(422, "end_date_required", "A date range needs an end date.")
        start_low, start_high = date_window(configuration, start_date, "day")
        end_low, end_high = date_window(configuration, end_date, "day")
        if end_high < start_low:
            raise ApiError(422, "invalid_date_range", "The end date must not precede the start date.")
        return start_low, end_high

    if end_date is not None:
        raise ApiError(422, "invalid_date_precision", "Only range dates may include an end date.")
    return date_window(configuration, start_date, precision)

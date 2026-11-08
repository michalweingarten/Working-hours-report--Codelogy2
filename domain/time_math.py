"""Conversions between minutes and the formats people read.

Everything inside the program is counted in whole minutes. These functions are the
only place that knows how to turn minutes into "08:30" or "6.50", and back.

worked_minutes() is the one formula for the hours of a row, used by the parser,
the transformation and the validation alike.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from domain.exceptions import TimeConversionError

# These are facts about time, not business rules, so they live here and not in config/.
MINUTES_PER_HOUR: Final[int] = 60
MINUTES_PER_DAY: Final[int] = 24 * MINUTES_PER_HOUR
LAST_HOUR_OF_DAY: Final[int] = 23
LAST_MINUTE_OF_HOUR: Final[int] = 59
DECIMAL_HOURS_PRECISION: Final[Decimal] = Decimal("0.01")  # 2 digits, like "6.50"


def clock_to_minutes(hour: int, minute: int) -> int:
    """08, 30 -> 510 (minutes since midnight)."""
    if not 0 <= hour <= LAST_HOUR_OF_DAY or not 0 <= minute <= LAST_MINUTE_OF_HOUR:
        raise TimeConversionError(f"Not a valid time of day: {hour}:{minute}")
    return hour * MINUTES_PER_HOUR + minute


def minutes_to_clock_text(minutes: int) -> str:
    """510 -> "08:30". Used for display; never for calculating."""
    if not 0 <= minutes < MINUTES_PER_DAY:
        raise TimeConversionError(f"Not a valid time of day: {minutes} minutes")
    hour, minute = divmod(minutes, MINUTES_PER_HOUR)
    return f"{hour:02d}:{minute:02d}"


def decimal_hours_to_minutes(hours: Decimal) -> int:
    """Decimal("6.50") -> 390. Rounds half up to a whole minute."""
    exact_minutes = hours * MINUTES_PER_HOUR
    return int(exact_minutes.to_integral_value(rounding=ROUND_HALF_UP))


def minutes_to_decimal_hours(minutes: int) -> Decimal:
    """390 -> Decimal("6.50"). Used for display; never for calculating."""
    hours = Decimal(minutes) / MINUTES_PER_HOUR
    return hours.quantize(DECIMAL_HOURS_PRECISION, rounding=ROUND_HALF_UP)


def worked_minutes(entry_minutes: int, exit_minutes: int, break_minutes: int | None = None) -> int:
    """Exit minus entry minus break. 08:00-15:00 with a 30-minute break -> 390."""
    return exit_minutes - entry_minutes - (break_minutes or 0)


def common_time_step(times: list[int], candidates: tuple[int, ...], share: float) -> int:
    """The largest step (in minutes) that at least `share` of the times are multiples of.

    [510, 720, 510, 720] -> 30 (8:30, 12:00);  [481, 665] -> 1 (8:01, 11:05).
    """
    for step in sorted(candidates, reverse=True):
        on_grid = sum(1 for minutes in times if minutes % step == 0)
        if times and on_grid >= share * len(times):
            return step
    return 1


def times_on_grid(minutes: int, max_shift: int, step: int) -> list[int]:
    """Every multiple of `step` within `max_shift` minutes of `minutes`.

    times_on_grid(510, 15, 15) -> [495, 510, 525]  (8:15, 8:30, 8:45)
    """
    first = -(-(minutes - max_shift) // step) * step  # the first multiple at or after the lower edge
    return list(range(first, minutes + max_shift + 1, step))

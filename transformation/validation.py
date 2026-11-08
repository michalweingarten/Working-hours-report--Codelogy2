"""The rules of a logical report (the invariants), as code.

Every rule returns a list of broken-rule messages instead of stopping at the first,
so one run shows EVERYTHING that is wrong (decision 27). ensure_valid_variant()
turns a non-empty list into one ValidationError.

Three groups of rules:
  row_violations      one row on its own
  report_violations   one report: its rows together, and its summary
  variant_violations  the new report against the original it was made from

A summary field that is None was not read (OCR) and is not checked.
"""
from decimal import ROUND_HALF_UP, Decimal

from config.rules import (
    MONEY_PRECISION_TEXT,
    OVERTIME_125_UNTIL_MINUTES,
    REGULAR_DAY_MINUTES,
    SHIFT_MAX_MINUTES,
    SHIFT_MIN_MINUTES,
    WORKDAY_EARLIEST_MINUTES,
    WORKDAY_LATEST_MINUTES,
)
from domain.exceptions import TimeConversionError, ValidationError
from domain.models import AttendanceReport, AttendanceRow, RowKind
from domain.time_math import MINUTES_PER_HOUR, minutes_to_clock_text, worked_minutes


def expected_pay(total_minutes: int, hourly_rate: Decimal) -> Decimal:
    """Pay from the EXACT minutes, not from the rounded hours.

    This is how the source computes it: n_r_10_n has 3,781 minutes x 32.35 = 2,038.59,
    while the rounded 63.02 hours x 32.35 would give 2,038.70.
    """
    pay = hourly_rate * Decimal(total_minutes) / MINUTES_PER_HOUR
    return pay.quantize(Decimal(MONEY_PRECISION_TEXT), rounding=ROUND_HALF_UP)


def expected_buckets(kind: RowKind, total: int) -> tuple[int, int, int, int]:
    """(100%, 125%, 150%, Shabbat) for a type B row, in minutes. As in the sources:
    Shabbat -> all at Shabbat; a holiday -> all at 150%; a regular day -> by the thresholds.
    """
    if kind is RowKind.SHABBAT:
        return 0, 0, 0, total
    if kind is RowKind.HOLIDAY:
        return 0, 0, total, 0
    regular = min(total, REGULAR_DAY_MINUTES)
    at_125 = min(max(total - REGULAR_DAY_MINUTES, 0), OVERTIME_125_UNTIL_MINUTES - REGULAR_DAY_MINUTES)
    at_150 = max(total - OVERTIME_125_UNTIL_MINUTES, 0)
    return regular, at_125, at_150, 0


def row_violations(row: AttendanceRow) -> list[str]:
    day = row.row_date.isoformat()
    has_entry, has_exit = row.entry_minutes is not None, row.exit_minutes is not None
    if has_entry != has_exit:
        return [f"{day}: has only one of entry and exit"]
    if not row.has_hours:
        return [] if not row.total_minutes else [f"{day}: no entry and exit, but a total of {row.total_minutes} minutes"]

    problems: list[str] = []
    entry, exit_ = row.entry_minutes, row.exit_minutes
    if exit_ <= entry:
        problems.append(f"{day}: exit {_clock(exit_)} is not after entry {_clock(entry)}")
    for name, minutes in (("entry", entry), ("exit", exit_)):
        if not WORKDAY_EARLIEST_MINUTES <= minutes <= WORKDAY_LATEST_MINUTES:
            problems.append(f"{day}: {name} {_clock(minutes)} is outside the working day")
    worked = worked_minutes(entry, exit_, row.break_minutes)
    if exit_ > entry and not SHIFT_MIN_MINUTES <= worked <= SHIFT_MAX_MINUTES:
        problems.append(f"{day}: a shift of {worked} minutes is not believable")
    if row.total_minutes != worked:
        problems.append(f"{day}: total is {row.total_minutes} minutes, but exit - entry - break = {worked}")

    buckets = (row.pay_100_minutes, row.pay_125_minutes, row.pay_150_minutes, row.shabbat_minutes)
    if any(bucket is not None for bucket in buckets):
        if sum(b or 0 for b in buckets) != row.total_minutes:
            problems.append(f"{day}: 100% + 125% + 150% + Shabbat is not the row total")
        elif row.total_minutes == worked and buckets != expected_buckets(row.kind, worked):
            problems.append(f"{day}: the split into 100/125/150/Shabbat does not follow the overtime rules")
    return problems


def report_violations(report: AttendanceReport) -> list[str]:
    problems = [problem for row in report.rows for problem in row_violations(row)]
    dates = [row.row_date for row in report.rows]
    if any(later <= earlier for earlier, later in zip(dates, dates[1:])):
        problems.append("dates are not in increasing order (or a date repeats)")

    month = report.header.month
    if month is not None:
        problems += [
            f"{d.isoformat()}: not in the month of the report ({month:%m/%Y})"
            for d in dates
            if (d.year, d.month) != (month.year, month.month)
        ]

    summary = report.summary
    rows_total = sum(row.total_minutes for row in report.rows if row.has_hours)
    days_with_hours = sum(1 for row in report.rows if row.has_hours)
    if summary.total_minutes is not None and summary.total_minutes != rows_total:
        problems.append(f"monthly total is {summary.total_minutes} minutes, but the rows add up to {rows_total}")
    if summary.days_count is not None and summary.days_count != days_with_hours:
        problems.append(f"working days is {summary.days_count}, but {days_with_hours} rows have hours")
    for name, field in (("100%", "pay_100_minutes"), ("125%", "pay_125_minutes"),
                        ("150%", "pay_150_minutes"), ("Shabbat", "shabbat_minutes")):
        total_of_column = getattr(summary, field)
        rows_sum = sum(getattr(row, field) or 0 for row in report.rows)
        if total_of_column is not None and total_of_column != rows_sum:
            problems.append(f"{name} total is {total_of_column} minutes, but the rows add up to {rows_sum}")
    if summary.total_break_minutes is not None:
        breaks = sum(row.break_minutes or 0 for row in report.rows)
        if summary.total_break_minutes != breaks:
            problems.append(f"total break is {summary.total_break_minutes} minutes, but the rows add up to {breaks}")
    if summary.hourly_rate is not None and summary.total_pay is not None and summary.total_minutes is not None:
        expected = expected_pay(summary.total_minutes, summary.hourly_rate)
        if summary.total_pay != expected:
            problems.append(f"total pay is {summary.total_pay}, but rate x hours = {expected}")
    return problems


def variant_violations(original: AttendanceReport, variant: AttendanceReport) -> list[str]:
    problems: list[str] = []
    if variant.report_type is not original.report_type:
        problems.append("the report type changed")
    if variant.header.month != original.header.month:
        problems.append("the month changed")
    if [(r.row_date, r.kind) for r in variant.rows] != [(r.row_date, r.kind) for r in original.rows]:
        problems.append("the days of the report (dates or Shabbat/holiday) changed")
    else:
        problems += [
            f"{old.row_date.isoformat()}: a day without hours was changed"
            for old, new in zip(original.rows, variant.rows)
            if not old.has_hours and new != old
        ]
    return problems


def ensure_valid_variant(original: AttendanceReport, variant: AttendanceReport) -> None:
    problems = report_violations(variant) + variant_violations(original, variant)
    if problems:
        raise ValidationError(problems)


def _clock(minutes: int) -> str:
    try:
        return minutes_to_clock_text(minutes)
    except TimeConversionError:  # an impossible time is exactly what is being reported
        return f"{minutes} minutes"

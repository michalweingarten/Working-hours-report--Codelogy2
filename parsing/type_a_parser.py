"""Station 3 for report type A (the simple report): raw OCR text -> AttendanceReport.

The OCR text of this report is very noisy: rows are lost, dates are broken
("17191229" instead of 17/9/22) and times lose their ":" ("12000"). So the parser
does not trust any single line. It rebuilds the WHOLE MONTH by the date sequence:

1. Find the month: the most common month/year among the dates that were read.
2. Anchor rows: lines with a readable date, kept only if the days keep increasing
   (a date that breaks the order, like "6/9" between 25/9 and 28/9, is an OCR error).
3. Fill the gaps between anchors: if a gap has exactly as many table lines as missing
   days, line i belongs to day i (each table row is one OCR line).
4. A day that is still unknown (or whose line has no letter or digit at all) gets what is usual for its weekday in this report,
   and a warning is logged, so the user knows the row was reconstructed.

Rules of type A seen in both samples: Shabbat rows never have hours, and a row's
total is exit minus entry.
"""
import calendar
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from statistics import median_low
from typing import Final

from config.rules import (
    SHIFT_MAX_MINUTES,
    SHIFT_MIN_MINUTES,
    WORKDAY_EARLIEST_MINUTES,
    WORKDAY_LATEST_MINUTES,
)
from domain.exceptions import ParsingError
from domain.models import AttendanceRow, ReportSummary, ReportType, RowKind
from domain.time_math import minutes_to_clock_text
from parsing.base_parser import BaseParser
from parsing.text_tools import DateParts, LineNumbers, find_dates, find_numbers

logger = logging.getLogger(__name__)

SATURDAY: Final[int] = 5  # date.weekday(): Monday is 0, Saturday is 5
TABLE_CELL_MARK: Final[str] = "|"
TABLE_HEADER_WORD: Final[str] = "שעת"  # the column header line: "יום  שעת  סה"כ"

# Labels in the box above the table (written without quotes, like the cleaned text).
DAYS_LABEL: Final[str] = "עבודה לחודש"
MONTHLY_HOURS_LABEL: Final[str] = "חודשיות"
HOURLY_RATE_LABEL: Final[str] = "מחיר לשעה"
TOTAL_PAY_LABEL: Final[str] = "לתשלום"

_SMALL_INTEGER: Final[re.Pattern[str]] = re.compile(r"(?<![\d.,])(\d{1,2})(?![\d.,])")
_DECIMAL_NUMBER: Final[re.Pattern[str]] = re.compile(r"(\d[\d,]*\.\d{2})")

Shift = tuple[int, int]  # (entry, exit) in minutes since midnight


@dataclass(frozen=True)
class _Reading:
    """One OCR line that may be a table row."""

    text: str
    date: DateParts | None
    numbers: LineNumbers


class TypeAParser(BaseParser):
    report_type = ReportType.TYPE_A

    def _parse_rows(self, lines: list[str]) -> list[AttendanceRow]:
        _box_lines, table_lines = self._split_box_and_table(lines)
        readings = [self._read(line) for line in table_lines if self._looks_like_row(line)]

        month_start = self._most_common_month(r.date for r in readings if r.date)
        days = self._days_of_month(month_start)
        assigned = self._assign_readings_to_days(days, readings, month_start)
        return self._build_rows(days, assigned)

    # --- reading lines --------------------------------------------------------
    @staticmethod
    def _split_box_and_table(lines: list[str]) -> tuple[list[str], list[str]]:
        for index, line in enumerate(lines):
            if TABLE_HEADER_WORD in line:
                return lines[:index], lines[index + 1 :]
        return [], lines  # header not found: treat everything as table

    @staticmethod
    def _read(line: str) -> _Reading:
        dates = find_dates(line)
        return _Reading(text=line, date=dates[0] if dates else None, numbers=find_numbers(line))

    @staticmethod
    def _looks_like_row(line: str) -> bool:
        numbers = find_numbers(line)
        return (
            TABLE_CELL_MARK in line
            or bool(find_dates(line))
            or bool(numbers.clock_times or numbers.hour_amounts)
        )

    # --- which day is each line? ---------------------------------------------
    @staticmethod
    def _days_of_month(month_start: date) -> list[date]:
        days_count = calendar.monthrange(month_start.year, month_start.month)[1]
        return [month_start + timedelta(days=offset) for offset in range(days_count)]

    def _assign_readings_to_days(
        self, days: list[date], readings: list[_Reading], month_start: date
    ) -> dict[date, _Reading | None]:
        """Day -> its OCR line. A day missing from the result is unknown."""
        anchors = self._anchor_dates(readings, month_start, len(days))
        assigned: dict[date, _Reading | None] = {
            days[day_number - 1]: readings[index] for index, day_number in anchors
        }
        # Gaps: before the first anchor, between anchors, after the last anchor.
        bounds = [(-1, 0)] + anchors + [(len(readings), len(days) + 1)]
        for (start_index, start_day), (end_index, end_day) in zip(bounds, bounds[1:]):
            gap_days = days[start_day : end_day - 1]
            gap_readings = readings[start_index + 1 : end_index]
            if gap_days and len(gap_days) == len(gap_readings):
                assigned.update(zip(gap_days, gap_readings))
        return assigned

    def _anchor_dates(
        self,
        readings: list[_Reading], month_start: date, days_count: int
    ) -> list[tuple[int, int]]:
        """(line index, day number) of the readable dates that keep the days increasing.

        The month in a date is not checked, because OCR damages it often (10/0/22),
        but the order of the days is (BaseParser._increasing_anchors).
        """
        candidates = [
            (index, r.date.day)
            for index, r in enumerate(readings)
            if r.date and r.date.year == month_start.year and 1 <= r.date.day <= days_count
        ]
        return self._increasing_anchors(candidates)

    # --- building the rows ----------------------------------------------------
    def _build_rows(
        self, days: list[date], assigned: dict[date, _Reading | None]
    ) -> list[AttendanceRow]:
        work_days = [day for day in days if day.weekday() != SATURDAY]
        clear_shifts = {
            day: shift
            for day in work_days
            if (reading := assigned.get(day)) and (shift := self._shift_from_times(reading.numbers))
        }
        if not clear_shifts:
            raise ParsingError("No row with a readable entry and exit time was found")
        typical = _TypicalShifts(clear_shifts)

        # Days whose line is known: a clear shift, a shift completed from part of the line,
        # or no hours at all (the line was there, but had no times in it).
        known: dict[date, Shift | None] = {}
        for day in work_days:
            if day in clear_shifts:
                known[day] = clear_shifts[day]
            elif day in assigned and _has_content(assigned[day]):
                known[day] = self._shift_from_partial(assigned[day].numbers, typical.for_day(day))
                if known[day]:
                    logger.warning("%s: only part of the row was readable; completed to %s",
                                   day.isoformat(), _describe(known[day]))

        rows: list[AttendanceRow] = []
        for day in days:
            if day.weekday() == SATURDAY:
                rows.append(AttendanceRow(row_date=day, kind=RowKind.SHABBAT))
                continue
            if day in known:
                shift = known[day]
            else:
                shift = typical.for_day(day) if _usually_works(day, known) else None
                logger.warning("%s: row not readable; filled as %s (usual for this weekday)",
                               day.isoformat(), _describe(shift))
            rows.append(self._row(day, shift))
        return rows

    @staticmethod
    def _row(day: date, shift: Shift | None) -> AttendanceRow:
        if shift is None:
            return AttendanceRow(row_date=day)
        entry, exit_ = shift
        return AttendanceRow(row_date=day, entry_minutes=entry, exit_minutes=exit_,
                             total_minutes=exit_ - entry)

    @staticmethod
    def _shift_from_times(numbers: LineNumbers) -> Shift | None:
        times = sorted(t for t in numbers.clock_times if _is_workday_time(t))
        if len(times) < 2:
            return None
        return _valid_shift((times[0], times[-1]))

    @staticmethod
    def _shift_from_partial(numbers: LineNumbers, typical: Shift) -> Shift | None:
        """One time and the row total, or only the total: complete with the usual times."""
        totals = [t for t in numbers.hour_amounts if SHIFT_MIN_MINUTES <= t <= SHIFT_MAX_MINUTES]
        if not totals:
            return None
        total = totals[0]
        times = [t for t in numbers.clock_times if _is_workday_time(t)]
        if not times:
            return _valid_shift((typical[0], typical[0] + total))
        time = times[0]
        closer_to_entry = abs(time - typical[0]) <= abs(time - typical[1])
        return _valid_shift((time, time + total) if closer_to_entry else (time - total, time))

    # --- the box above the table ---------------------------------------------
    def _parse_summary(self, lines: list[str], rows: tuple[AttendanceRow, ...]) -> ReportSummary:
        box_lines, _table_lines = self._split_box_and_table(lines)

        def line_with(label: str) -> str:
            return next((line for line in box_lines if label in line), "")

        days_match = _SMALL_INTEGER.search(line_with(DAYS_LABEL).replace(DAYS_LABEL, ""))
        return ReportSummary(
            days_count=int(days_match.group(1)) if days_match else None,
            hourly_rate=_decimal_in(line_with(HOURLY_RATE_LABEL)),
            total_pay=_decimal_in(line_with(TOTAL_PAY_LABEL)),
            total_minutes=None,  # computed from the rows by the transformation
        )


class _TypicalShifts:
    """What is usual in this report: per weekday, and for the whole report."""

    def __init__(self, clear_shifts: dict[date, Shift]) -> None:
        self._overall = _median_shift(list(clear_shifts.values()))
        by_weekday: dict[int, list[Shift]] = {}
        for day, shift in clear_shifts.items():
            by_weekday.setdefault(day.weekday(), []).append(shift)
        self._by_weekday = {weekday: _median_shift(shifts) for weekday, shifts in by_weekday.items()}

    def for_day(self, day: date) -> Shift:
        return self._by_weekday.get(day.weekday(), self._overall)


def _usually_works(day: date, known: dict[date, Shift | None]) -> bool:
    """Of the known days with the same weekday, did at least half have hours?"""
    same_weekday = [shift for d, shift in known.items() if d.weekday() == day.weekday()]
    if not same_weekday:
        return True
    worked = sum(1 for shift in same_weekday if shift is not None)
    return worked * 2 >= len(same_weekday)


def _has_content(reading: _Reading) -> bool:
    """A line with no letter or digit at all (only "|") is a LOST row, not an empty one.

    It still counts in the date sequence (step 3 of the module doc), but it says
    nothing about the day, so the day is treated as unknown.
    """
    return any(char.isalnum() for char in reading.text)


def _median_shift(shifts: list[Shift]) -> Shift:
    return median_low(s[0] for s in shifts), median_low(s[1] for s in shifts)


def _is_workday_time(minutes: int) -> bool:
    return WORKDAY_EARLIEST_MINUTES <= minutes <= WORKDAY_LATEST_MINUTES


def _valid_shift(shift: Shift) -> Shift | None:
    entry, exit_ = shift
    if not (_is_workday_time(entry) and _is_workday_time(exit_)):
        return None
    return shift if SHIFT_MIN_MINUTES <= exit_ - entry <= SHIFT_MAX_MINUTES else None


def _decimal_in(line: str) -> Decimal | None:
    match = _DECIMAL_NUMBER.search(line)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _describe(shift: Shift | None) -> str:
    if shift is None:
        return "a day without hours"
    return f"{minutes_to_clock_text(shift[0])}-{minutes_to_clock_text(shift[1])}"

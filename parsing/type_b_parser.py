"""Station 3 for report type B (the detailed report): raw OCR text -> AttendanceReport.

What the OCR gives in type B (docs/ocr_notes.md):
* The times and the amounts are read well, and in the order of the columns, so they
  are read by POSITION: entry, exit, break / total, 100%, 125%, 150%, Shabbat. Never by
  "the smallest time is the entry" (the break is the smallest).
* But the OCR sometimes writes a whole line reversed, left to right (a_r_25 on Windows):
  "0.00 0.00 0.00 7.50 7.50 00:30 16:00 08:00 ... 3". So the direction of every line is
  found first, by the rule of the report itself: the total is the sum of 100% + 125% +
  150% + Shabbat, and only one direction keeps it. Then the columns are read by position.
* The dates are mostly lost ("2 יום ראשון"), and a type B report lists only the days
  that were worked, so the month cannot be rebuilt day by day as in type A.
  Instead every row gets the first date that fits it, after the row before it:
  its own date if it was read, else the day name it shows, and a row with Shabbat
  hours falls on a Saturday. A row with no clue at all gets the next weekday, with
  a warning.

A row's total is exit - entry - break (the rule of the report), and the amounts the
OCR read are kept only if they add up to it.
"""
import calendar
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from domain.models import AttendanceRow, ReportHeader, ReportSummary, ReportType, RowKind
from domain.time_math import worked_minutes
from parsing.base_parser import BaseParser
from parsing.text_tools import DateParts, find_clock_times, find_dates, find_hour_amounts, find_weekday

logger = logging.getLogger(__name__)

SATURDAY: Final[int] = 5  # date.weekday()
TIMES_IN_ROW: Final[int] = 3  # entry, exit, break
AMOUNTS_IN_ROW: Final[int] = 5  # total, 100%, 125%, 150%, Shabbat
AMOUNTS_IN_TOTALS_LINE: Final[int] = 5
COMPANY_MARK: Final[str] = "בעמ"  # 'בע"מ' after the quotes were cleaned away
COMPANY_SUFFIX: Final[str] = 'בע"מ'
DAYS_LABEL: Final[str] = "ימים"
BONUS_LABEL: Final[str] = "בונוס"
TRAVEL_LABEL: Final[str] = "נסיעות"
NOT_A_WORKPLACE: Final[frozenset[str]] = frozenset(
    {"יום", "ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"}
)

_HEBREW_WORD: Final[re.Pattern[str]] = re.compile(r"^[\u05d0-\u05ea]{2,}$")
_LEADING_INTEGER: Final[re.Pattern[str]] = re.compile(r"^\s*(\d{1,2})(?![\d.:])")
_TRAILING_INTEGER: Final[re.Pattern[str]] = re.compile(r"(?<![\d.:])(\d{1,2})\s*$")
_WHOLE_NUMBER: Final[re.Pattern[str]] = re.compile(r"(?<![\d.])(\d+)(?![\d.])")
_LATIN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class _Reading:
    """One table row as the OCR gave it."""

    text: str
    date: DateParts | None
    weekday: int | None
    times: tuple[int, ...]  # entry, exit, break
    amounts: tuple[int, ...]  # total, 100%, 125%, 150%, Shabbat (as many as were read)

    @property
    def has_shabbat_hours(self) -> bool:
        return len(self.amounts) == AMOUNTS_IN_ROW and self.amounts[4] > 0


class TypeBParser(BaseParser):
    report_type = ReportType.TYPE_B

    # --- rows -----------------------------------------------------------------
    def _parse_rows(self, lines: list[str]) -> list[AttendanceRow]:
        readings = [self._read(line) for line in lines if len(find_clock_times(line)) >= TIMES_IN_ROW]
        if not readings:
            return []
        month_start = self._most_common_month(r.date for r in readings if r.date)
        dates = self._assign_dates(readings, month_start)
        workplace = self._common_workplace(readings)
        return [self._row(reading, day, workplace) for reading, day in zip(readings, dates)]

    @staticmethod
    def _read(line: str) -> _Reading:
        dates = find_dates(line)
        times, amounts = _columns_in_reading_order(line)
        return _Reading(
            text=line,
            date=dates[0] if dates else None,
            weekday=find_weekday(line),
            times=times,
            amounts=amounts,
        )

    @staticmethod
    def _row(reading: _Reading, day: date, workplace: str | None) -> AttendanceRow:
        entry, exit_, break_ = reading.times
        total = worked_minutes(entry, exit_, break_)
        buckets: tuple[int | None, ...] = (None, None, None, None)
        if len(reading.amounts) == AMOUNTS_IN_ROW and sum(reading.amounts[1:]) == total:
            buckets = reading.amounts[1:]
        else:
            logger.warning("%s: the 100%%/125%%/150%%/Shabbat columns could not be read; "
                           "they are computed again from the hours", day.isoformat())
        pay_100, pay_125, pay_150, shabbat = buckets
        return AttendanceRow(
            row_date=day,
            kind=_kind(day, total, pay_100, pay_150),
            entry_minutes=entry,
            exit_minutes=exit_,
            total_minutes=total,
            workplace=workplace,
            break_minutes=break_,
            pay_100_minutes=pay_100,
            pay_125_minutes=pay_125,
            pay_150_minutes=pay_150,
            shabbat_minutes=shabbat,
        )

    # --- dates ----------------------------------------------------------------
    def _assign_dates(self, readings: list[_Reading], month_start: date) -> list[date]:
        days_count = calendar.monthrange(month_start.year, month_start.month)[1]
        anchors = dict(self._increasing_anchors([
            (index, r.date.day)
            for index, r in enumerate(readings)
            if r.date and (r.date.year, r.date.month) == (month_start.year, month_start.month)
            and 1 <= r.date.day <= days_count
        ]))
        days: list[int] = []
        for index, reading in enumerate(readings):
            if index in anchors:
                days.append(anchors[index])
                continue
            previous = days[-1] if days else 0
            next_anchor = min((day for i, day in anchors.items() if i > index), default=days_count + 1)
            days.append(self._first_fitting_day(reading, month_start, previous, next_anchor))
        return [month_start.replace(day=day) for day in days]

    @staticmethod
    def _first_fitting_day(reading: _Reading, month_start: date, previous: int, next_anchor: int) -> int:
        def fits(day: int) -> bool:
            weekday = month_start.replace(day=day).weekday()
            if reading.weekday is not None:
                return weekday == reading.weekday
            return (weekday == SATURDAY) == reading.has_shabbat_hours

        candidates = range(previous + 1, next_anchor)
        day = next((d for d in candidates if fits(d)), None)
        if reading.weekday is None:
            logger.warning("a row without a readable date or day name was placed on %s",
                           month_start.replace(day=day or previous + 1).isoformat())
        if day is None:
            logger.warning("no date fits the row after day %d; the next day is used", previous)
            day = previous + 1
        return day

    # --- the rest of the page -------------------------------------------------
    @staticmethod
    def _common_workplace(readings: list[_Reading]) -> str | None:
        """The place column: the Hebrew word before the times that most rows share."""
        words = Counter(
            token.strip("|")
            for r in readings
            for token in r.text.split()
            if _HEBREW_WORD.match(token.strip("|")) and token.strip("|") not in NOT_A_WORKPLACE
        )
        return words.most_common(1)[0][0] if words else None

    def _parse_header(self, lines: list[str], rows: tuple[AttendanceRow, ...]) -> ReportHeader:
        company_line = next((line for line in lines if COMPANY_MARK in line), None)
        company = None
        if company_line:
            words = [w for w in company_line.split() if not _LATIN.search(w)]
            company = " ".join(words).replace(COMPANY_MARK, COMPANY_SUFFIX)
        return ReportHeader(company_name=company, month=rows[0].row_date.replace(day=1))

    def _parse_summary(self, lines: list[str], rows: tuple[AttendanceRow, ...]) -> ReportSummary:
        last_row_index = max(i for i, line in enumerate(lines) if len(find_clock_times(line)) >= TIMES_IN_ROW)
        totals_line = next(
            (line for line in lines[last_row_index + 1:]
             if len(find_hour_amounts(line, side="all")) >= AMOUNTS_IN_TOTALS_LINE),
            "",
        )
        amounts = _in_column_order(find_hour_amounts(totals_line, side="all"))
        breaks = find_clock_times(totals_line)
        days = _LEADING_INTEGER.match(totals_line) or _TRAILING_INTEGER.search(totals_line)
        total, pay_100, pay_125, pay_150, shabbat = amounts if amounts else [None] * AMOUNTS_IN_TOTALS_LINE
        return ReportSummary(
            days_count=int(days.group(1)) if days else None,
            total_minutes=total,
            pay_100_minutes=pay_100,
            pay_125_minutes=pay_125,
            pay_150_minutes=pay_150,
            shabbat_minutes=shabbat,
            total_break_minutes=breaks[0] if breaks else None,
            bonus=_number_after(lines, BONUS_LABEL),
            travel=_number_after(lines, TRAVEL_LABEL),
        )


def _adds_up(amounts: list[int]) -> bool:
    """total, 100%, 125%, 150%, Shabbat: the first is the sum of the other four."""
    return len(amounts) >= AMOUNTS_IN_ROW and amounts[0] == sum(amounts[1:AMOUNTS_IN_ROW])


def _in_column_order(amounts: list[int]) -> list[int]:
    """The five amounts (total, 100%, 125%, 150%, Shabbat) in column order, whichever way
    the line was written. Empty if neither direction adds up."""
    if _adds_up(amounts):
        return amounts[:AMOUNTS_IN_ROW]
    backwards = amounts[::-1]
    if _adds_up(backwards):
        return backwards[:AMOUNTS_IN_ROW]
    return []


def _columns_in_reading_order(line: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(entry, exit, break) and (total, 100%, 125%, 150%, Shabbat) of a row, by column position.

    A row read right to left has its amounts AFTER the times; a reversed row has them
    BEFORE the times, in reverse. The direction whose amounts add up wins. If neither
    adds up (an amount was misread), the side with more amounts decides.
    """
    times = find_clock_times(line)
    after = find_hour_amounts(line, side="after")
    before = find_hour_amounts(line, side="before")[::-1]
    if _adds_up(after):
        reversed_line = False
    elif _adds_up(before):
        reversed_line = True
    else:
        reversed_line = len(before) > len(after)
    if reversed_line:
        return tuple(times[::-1][:TIMES_IN_ROW]), tuple(before[:AMOUNTS_IN_ROW])
    return tuple(times[:TIMES_IN_ROW]), tuple(after[:AMOUNTS_IN_ROW])


def _kind(day: date, total: int, pay_100: int | None, pay_150: int | None) -> RowKind:
    """Shabbat by the calendar; a holiday is a weekday paid entirely at 150% (17/10/22)."""
    if day.weekday() == SATURDAY:
        return RowKind.SHABBAT
    if pay_100 == 0 and pay_150 == total and total > 0:
        return RowKind.HOLIDAY
    return RowKind.WORK


def _number_after(lines: list[str], label: str) -> Decimal | None:
    line = next((line for line in lines if label in line), "")
    match = _WHOLE_NUMBER.search(line.replace(label, ""))
    return Decimal(match.group(1)) if match else None

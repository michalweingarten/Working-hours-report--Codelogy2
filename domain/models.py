"""The shared language of the whole program.

From station 3 (the parser) onward, nobody knows which PDF a report came from.
Everyone speaks only in the types defined here.

Rules of this module:
* Every class is a frozen dataclass: an object cannot be changed after it is built.
  "Changing" a report means building a new one (see dataclasses.replace).
* A time of day and an amount of hours are both integers, counted in MINUTES.
  Time of day: minutes since midnight (08:30 -> 510).
  Amount of hours: minutes (6.50 hours -> 390). See time_math.py for conversions.
* A field that exists only in one report type is optional (None in the other type).
* This module only HOLDS data. Checking that the data is logical lives in
  transformation/validation.py.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum, auto


class ReportType(Enum):
    """Which of the two supported report layouts a report came from."""

    TYPE_A = auto()  # the simple report
    TYPE_B = auto()  # the detailed report


class RowKind(Enum):
    """What kind of day a row describes. It says nothing about whether it has hours."""

    WORK = auto()
    SHABBAT = auto()
    HOLIDAY = auto()


@dataclass(frozen=True)
class AttendanceRow:
    """One day in the report."""

    # --- fields that exist in both report types -------------------------------
    row_date: date
    kind: RowKind = RowKind.WORK
    entry_minutes: int | None = None  # None on a day without hours (Shabbat/holiday in type A)
    exit_minutes: int | None = None
    total_minutes: int | None = None  # the row's total hours
    notes: str = ""

    # --- fields that exist only in type B (None in type A) --------------------
    workplace: str | None = None
    break_minutes: int | None = None
    pay_100_minutes: int | None = None
    pay_125_minutes: int | None = None
    pay_150_minutes: int | None = None
    shabbat_minutes: int | None = None

    @property
    def has_hours(self) -> bool:
        """True when the row has both an entry and an exit time."""
        return self.entry_minutes is not None and self.exit_minutes is not None


@dataclass(frozen=True)
class ReportHeader:
    """Who and when: the details printed above the table."""

    employee_name: str | None = None
    company_name: str | None = None  # printed in type B
    month: date | None = None  # always the first day of the month


@dataclass(frozen=True)
class ReportSummary:
    """The totals of the report. Some fields exist only in one report type."""

    days_count: int | None = None
    total_minutes: int | None = None
    # --- type A: money -------------------------------------------------------
    hourly_rate: Decimal | None = None
    total_pay: Decimal | None = None
    # --- type B: breakdown of the hours --------------------------------------
    pay_100_minutes: int | None = None
    pay_125_minutes: int | None = None
    pay_150_minutes: int | None = None
    shabbat_minutes: int | None = None
    total_break_minutes: int | None = None
    bonus: Decimal | None = None
    travel: Decimal | None = None


@dataclass(frozen=True)
class AttendanceReport:
    """The contract between the stations: a whole report, independent of its source PDF."""

    report_type: ReportType
    header: ReportHeader
    rows: tuple[AttendanceRow, ...]  # a tuple, not a list, so it cannot be changed either
    summary: ReportSummary

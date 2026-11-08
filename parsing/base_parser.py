"""BaseParser: the parse() flow shared by every report type (Template Method).

parse() is written once and fixes the order of the work:
    clean the text -> split it into lines -> read the rows -> check there are rows
    -> read the header -> read the summary -> build the AttendanceReport.
A subclass fills in only the steps that differ between report types: how the rows
are read (_parse_rows) and how the summary is read (_parse_summary).

The helpers at the bottom (the month of the report, the readable dates that keep
increasing) are used by both parsers, so they are written once, here.
"""
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterable
from datetime import date

from domain.exceptions import ParsingError
from domain.models import AttendanceReport, AttendanceRow, ReportHeader, ReportSummary, ReportType
from parsing.text_tools import DateParts, clean_text

MONTHS_IN_YEAR = 12


class BaseParser(ABC):
    report_type: ReportType

    def parse(self, raw_text: str) -> AttendanceReport:
        lines = [line for line in clean_text(raw_text).splitlines() if line.strip()]
        rows = tuple(self._parse_rows(lines))
        if not rows:
            raise ParsingError(f"No attendance rows found ({self.report_type.name})")
        return AttendanceReport(
            report_type=self.report_type,
            header=self._parse_header(lines, rows),
            rows=rows,
            summary=self._parse_summary(lines, rows),
        )

    # --- the steps that differ between report types ---------------------------
    @abstractmethod
    def _parse_rows(self, lines: list[str]) -> list[AttendanceRow]:
        """Every row of the table, in order."""

    @abstractmethod
    def _parse_summary(self, lines: list[str], rows: tuple[AttendanceRow, ...]) -> ReportSummary:
        """What the summary of the source says. A value that could not be read is None."""

    # --- a step with a default that a subclass may replace --------------------
    def _parse_header(self, lines: list[str], rows: tuple[AttendanceRow, ...]) -> ReportHeader:
        return ReportHeader(month=rows[0].row_date.replace(day=1))

    # --- helpers shared by the parsers ----------------------------------------
    @staticmethod
    def _most_common_month(dates: Iterable[DateParts]) -> date:
        """The first day of the month that most readable dates belong to."""
        months = Counter((d.year, d.month) for d in dates if 1 <= d.month <= MONTHS_IN_YEAR)
        if not months:
            raise ParsingError("No readable date found, so the month of the report is unknown")
        (year, month), _count = months.most_common(1)[0]
        return date(year, month, 1)

    @staticmethod
    def _increasing_anchors(candidates: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """The longest run of (line index, day) whose days keep increasing.

        A readable date that breaks the order (6/9 between 25/9 and 28/9) is an OCR error.
        """
        best: list[list[tuple[int, int]]] = []
        for position, candidate in enumerate(candidates):
            longest_before = max(
                (best[earlier] for earlier in range(position) if candidates[earlier][1] < candidate[1]),
                key=len,
                default=[],
            )
            best.append(longest_before + [candidate])
        return max(best, key=len, default=[])

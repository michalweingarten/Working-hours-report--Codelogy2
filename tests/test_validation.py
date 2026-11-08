"""Tests for transformation/validation.py: one test per rule, and the real numbers."""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from domain.exceptions import ValidationError
from domain.models import AttendanceReport, AttendanceRow, ReportHeader, ReportSummary, ReportType, RowKind
from transformation.validation import (
    ensure_valid_variant,
    expected_buckets,
    expected_pay,
    report_violations,
    row_violations,
    variant_violations,
)

EIGHT, EIGHT_THIRTY, NOON, THREE_PM = 480, 510, 720, 900


def work_row(day: int, entry: int = EIGHT_THIRTY, exit_: int = NOON, **more) -> AttendanceRow:
    total = more.pop("total_minutes", exit_ - entry - (more.get("break_minutes") or 0))
    return AttendanceRow(row_date=date(2022, 9, day), entry_minutes=entry, exit_minutes=exit_,
                         total_minutes=total, **more)


def valid_report() -> AttendanceReport:
    rows = (work_row(1), work_row(2), AttendanceRow(row_date=date(2022, 9, 3), kind=RowKind.SHABBAT))
    return AttendanceReport(
        report_type=ReportType.TYPE_A,
        header=ReportHeader(month=date(2022, 9, 1)),
        rows=rows,
        summary=ReportSummary(days_count=2, total_minutes=420, hourly_rate=Decimal("30.65"),
                              total_pay=Decimal("214.55")),
    )


class TestAValidReport:
    def test_has_no_violations(self):
        assert report_violations(valid_report()) == []

    def test_a_row_without_hours_is_fine(self):
        assert row_violations(AttendanceRow(row_date=date(2022, 9, 26))) == []


ROW_CASES = {
    "only entry": (AttendanceRow(row_date=date(2022, 9, 1), entry_minutes=EIGHT_THIRTY), "only one of entry and exit"),
    "exit before entry": (work_row(1, entry=NOON, exit_=EIGHT_THIRTY), "is not after entry"),
    "time at night": (work_row(1, entry=60, exit_=300), "outside the working day"),
    "shift too short": (work_row(1, entry=EIGHT_THIRTY, exit_=EIGHT_THIRTY + 5), "not believable"),
    "wrong total": (work_row(1, total_minutes=200), "exit - entry - break"),
    "break not taken off": (work_row(1, entry=EIGHT, exit_=THREE_PM, break_minutes=30, total_minutes=420),
                            "exit - entry - break"),
    "total without hours": (AttendanceRow(row_date=date(2022, 9, 1), total_minutes=210), "no entry and exit"),
    "buckets do not add up": (work_row(1, pay_100_minutes=100, pay_125_minutes=0, pay_150_minutes=0,
                                       shabbat_minutes=0), "100% + 125% + 150%"),
}


class TestRowRules:
    @pytest.mark.parametrize("row, expected", ROW_CASES.values(), ids=ROW_CASES.keys())
    def test_rule_is_caught(self, row, expected):
        problems = row_violations(row)
        assert any(expected in problem for problem in problems), problems

    def test_type_b_row_with_break_and_buckets_is_fine(self):
        row = work_row(2, entry=EIGHT, exit_=THREE_PM, break_minutes=30,
                       pay_100_minutes=390, pay_125_minutes=0, pay_150_minutes=0, shabbat_minutes=0)
        assert row.total_minutes == 390
        assert row_violations(row) == []


REPORT_CASES = {
    "monthly total": (lambda r: replace(r, summary=replace(r.summary, total_minutes=999)), "monthly total"),
    "days count": (lambda r: replace(r, summary=replace(r.summary, days_count=20)), "working days"),
    "pay": (lambda r: replace(r, summary=replace(r.summary, total_pay=Decimal("1.00"))), "total pay"),
    "date order": (lambda r: replace(r, rows=(r.rows[1], r.rows[0], r.rows[2])), "increasing order"),
    "other month": (lambda r: replace(r, header=ReportHeader(month=date(2022, 10, 1))), "not in the month"),
}


class TestReportRules:
    @pytest.mark.parametrize("break_it, expected", REPORT_CASES.values(), ids=REPORT_CASES.keys())
    def test_rule_is_caught(self, break_it, expected):
        problems = report_violations(break_it(valid_report()))
        assert any(expected in problem for problem in problems), problems

    def test_a_summary_field_that_was_not_read_is_not_checked(self):
        report = valid_report()
        unread = replace(report, summary=ReportSummary())
        assert report_violations(unread) == []


class TestVariantRules:
    def test_month_change_is_caught(self):
        original = valid_report()
        moved = replace(original, header=ReportHeader(month=date(2022, 10, 1)))
        assert "the month changed" in variant_violations(original, moved)

    def test_change_of_days_is_caught(self):
        original = valid_report()
        fewer = replace(original, rows=original.rows[:2])
        assert any("days of the report" in p for p in variant_violations(original, fewer))

    def test_change_of_a_day_without_hours_is_caught(self):
        original = replace(valid_report(), rows=valid_report().rows + (AttendanceRow(row_date=date(2022, 9, 26)),))
        noted = replace(original, rows=original.rows[:3] + (AttendanceRow(row_date=date(2022, 9, 26), notes="x"),))
        assert any("without hours was changed" in p for p in variant_violations(original, noted))


class TestAllViolationsTogether:
    def test_error_lists_every_broken_rule(self):
        original = valid_report()
        broken = replace(original, summary=replace(original.summary, total_pay=Decimal("1.00"), days_count=9))
        with pytest.raises(ValidationError) as caught:
            ensure_valid_variant(original, broken)
        assert len(caught.value.violations) == 2
        assert "2 rule(s)" in str(caught.value)

    def test_valid_variant_passes(self):
        ensure_valid_variant(valid_report(), valid_report())


class TestRealNumbersFromTheSource:
    def test_pay_is_from_exact_minutes_as_in_n_r_10_n(self):
        # 3,781 minutes x 32.35 = 2,038.59 (printed in the source); 63.02 x 32.35 would be 2,038.70.
        assert expected_pay(3781, Decimal("32.35")) == Decimal("2038.59")

    def test_n_r_5_n_pay(self):
        assert expected_pay(84 * 60, Decimal("30.65")) == Decimal("2574.60")


class TestOvertimeSplit:
    """Decision 43: up to 8 hours 100%, 8-9 hours 125%, above 9 hours 150%."""

    @pytest.mark.parametrize("total_hours_minutes, expected", [
        (390, (390, 0, 0, 0)),     # 6.50: all regular
        (480, (480, 0, 0, 0)),     # exactly 8
        (510, (480, 30, 0, 0)),    # 8.50
        (540, (480, 60, 0, 0)),    # exactly 9
        (600, (480, 60, 60, 0)),   # 10
    ])
    def test_regular_day(self, total_hours_minutes, expected):
        assert expected_buckets(RowKind.WORK, total_hours_minutes) == expected

    def test_shabbat_is_all_shabbat(self):
        assert expected_buckets(RowKind.SHABBAT, 600) == (0, 0, 0, 600)

    def test_holiday_is_all_150(self):
        assert expected_buckets(RowKind.HOLIDAY, 390) == (0, 0, 390, 0)

    def test_wrong_split_is_caught(self):
        row = work_row(2, entry=EIGHT, exit_=THREE_PM, break_minutes=30,
                       pay_100_minutes=0, pay_125_minutes=390, pay_150_minutes=0, shabbat_minutes=0)
        assert any("overtime rules" in p for p in row_violations(row))


class TestTypeBSummaryRules:
    def test_column_total_and_breaks_are_checked(self):
        row = work_row(2, entry=EIGHT, exit_=THREE_PM, break_minutes=30,
                       pay_100_minutes=390, pay_125_minutes=0, pay_150_minutes=0, shabbat_minutes=0)
        report = AttendanceReport(ReportType.TYPE_B, ReportHeader(month=date(2022, 9, 1)), (row,),
                                  ReportSummary(pay_100_minutes=100, total_break_minutes=45))
        problems = report_violations(report)
        assert any("100% total" in p for p in problems)
        assert any("total break" in p for p in problems)

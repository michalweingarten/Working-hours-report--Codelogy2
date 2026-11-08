"""Tests for domain/models.py."""
from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from domain.models import (
    AttendanceReport,
    AttendanceRow,
    ReportHeader,
    ReportSummary,
    ReportType,
    RowKind,
)

SOME_DAY = date(2022, 9, 1)


def make_row(**overrides) -> AttendanceRow:
    fields = {"row_date": SOME_DAY, "entry_minutes": 510, "exit_minutes": 720, "total_minutes": 210}
    fields.update(overrides)
    return AttendanceRow(**fields)


class TestAttendanceRow:
    def test_type_a_row_leaves_type_b_fields_empty(self):
        row = make_row()
        assert row.break_minutes is None
        assert row.pay_100_minutes is None
        assert row.pay_125_minutes is None
        assert row.pay_150_minutes is None
        assert row.shabbat_minutes is None
        assert row.workplace is None

    def test_default_kind_is_work(self):
        assert make_row().kind is RowKind.WORK

    def test_row_is_frozen(self):
        row = make_row()
        with pytest.raises(FrozenInstanceError):
            row.entry_minutes = 600

    def test_replace_builds_a_new_row_and_keeps_the_original(self):
        original = make_row()
        changed = replace(original, entry_minutes=540)
        assert changed.entry_minutes == 540
        assert original.entry_minutes == 510
        assert changed is not original

    def test_row_with_hours(self):
        assert make_row().has_hours is True

    def test_shabbat_row_without_hours(self):
        row = AttendanceRow(row_date=SOME_DAY, kind=RowKind.SHABBAT)
        assert row.has_hours is False

    def test_has_hours_needs_both_entry_and_exit(self):
        assert make_row(exit_minutes=None).has_hours is False

    def test_rows_with_same_values_are_equal(self):
        assert make_row() == make_row()


class TestAttendanceReport:
    def test_report_is_frozen(self):
        report = AttendanceReport(
            report_type=ReportType.TYPE_A,
            header=ReportHeader(),
            rows=(make_row(),),
            summary=ReportSummary(),
        )
        with pytest.raises(FrozenInstanceError):
            report.report_type = ReportType.TYPE_B

    def test_replace_rows_leaves_the_original_report_unchanged(self):
        original = AttendanceReport(ReportType.TYPE_A, ReportHeader(), (make_row(),), ReportSummary())
        new_rows = tuple(replace(row, entry_minutes=540) for row in original.rows)
        updated = replace(original, rows=new_rows)
        assert original.rows[0].entry_minutes == 510
        assert updated.rows[0].entry_minutes == 540

    def test_report_types_are_distinct(self):
        assert ReportType.TYPE_A is not ReportType.TYPE_B

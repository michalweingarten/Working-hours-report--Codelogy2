"""Tests for transformation/: the service loop, the per-row seed and the type A strategy.

The original is not changed, the run is repeatable, and every derived number is
computed again. The rules themselves are tested in test_validation.py.
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal
from random import Random

import pytest

from config.rules import TRANSFORM_RULES, TransformRules
from domain.exceptions import TransformationError
from domain.models import AttendanceReport, AttendanceRow, ReportHeader, ReportSummary, ReportType, RowKind
from transformation.base_strategy import BaseTransformationStrategy
from transformation.service import TransformationService
from transformation.type_a_strategy import TypeATransformationStrategy
from transformation.type_b_strategy import TypeBTransformationStrategy

EIGHT_THIRTY, NOON = 510, 720
RULES_A = TRANSFORM_RULES[ReportType.TYPE_A]


def work_row(day: int) -> AttendanceRow:
    return AttendanceRow(row_date=date(2022, 9, day), entry_minutes=EIGHT_THIRTY, exit_minutes=NOON,
                         total_minutes=NOON - EIGHT_THIRTY)


def make_report(hourly_rate: Decimal | None = Decimal("30.65")) -> AttendanceReport:
    rows = tuple(work_row(day) for day in range(4, 9)) + (
        AttendanceRow(row_date=date(2022, 9, 10), kind=RowKind.SHABBAT),
        AttendanceRow(row_date=date(2022, 9, 26)),  # a holiday: no hours
    )
    return AttendanceReport(
        report_type=ReportType.TYPE_A,
        header=ReportHeader(month=date(2022, 9, 1)),
        rows=rows,
        summary=ReportSummary(days_count=5, total_minutes=1050, hourly_rate=hourly_rate),
    )


def make_service(seed: int = 42) -> TransformationService:
    return TransformationService(strategies={ReportType.TYPE_A: TypeATransformationStrategy()}, seed=seed)


@pytest.fixture
def report() -> AttendanceReport:
    return make_report()


@pytest.fixture
def variant(report) -> AttendanceReport:
    return make_service().transform(report)


class TestTheOriginal:
    def test_original_is_not_changed(self, report):
        before = make_report()
        make_service().transform(report)
        assert report == before

    def test_variant_is_different(self, report, variant):
        assert variant.rows != report.rows


class TestRepeatable:
    def test_same_seed_same_result(self, report):
        assert make_service(7).transform(report) == make_service(7).transform(report)

    def test_other_seed_other_result(self, report):
        assert make_service(1).transform(report) != make_service(2).transform(report)

    def test_rows_do_not_affect_each_other(self, report):
        # With one generator for the whole report, removing a row would move every row after it.
        # With a generator per row (seed + date), the other rows stay exactly the same.
        shorter = replace(report, rows=report.rows[1:])
        full = make_service().transform(report).rows
        without_first = make_service().transform(shorter).rows
        assert full[1:] == without_first


class TestRows:
    def test_entry_and_exit_move_by_at_most_the_rules(self, report, variant):
        for old, new in zip(report.rows, variant.rows):
            if old.has_hours:
                assert abs(new.entry_minutes - old.entry_minutes) <= RULES_A.entry_shift_minutes
                assert abs(new.exit_minutes - old.exit_minutes) <= RULES_A.exit_shift_minutes

    def test_row_total_is_computed_again(self, variant):
        for row in variant.rows:
            if row.has_hours:
                assert row.exit_minutes > row.entry_minutes
                assert row.total_minutes == row.exit_minutes - row.entry_minutes

    def test_hours_change_not_only_the_times(self, report, variant):
        assert [r.total_minutes for r in variant.rows] != [r.total_minutes for r in report.rows]

    def test_shabbat_and_holiday_stay_without_hours(self, report, variant):
        assert variant.rows[-2:] == report.rows[-2:]
        assert not any(row.has_hours for row in variant.rows[-2:])

    def test_dates_and_kinds_do_not_change(self, report, variant):
        assert [(r.row_date, r.kind) for r in variant.rows] == [(r.row_date, r.kind) for r in report.rows]

    def test_illogical_move_keeps_the_original_row(self):
        short = AttendanceRow(row_date=date(2022, 9, 4), entry_minutes=600, exit_minutes=620, total_minutes=20)
        wide = TransformRules(entry_shift_minutes=60, exit_shift_minutes=60)
        moved = TypeATransformationStrategy().transform_row(short, wide, Random(3))
        assert moved == short or moved.exit_minutes - moved.entry_minutes >= 15

    def test_a_rule_change_is_one_value(self, report):
        frozen_times = TransformRules(entry_shift_minutes=0, exit_shift_minutes=0)
        service = TransformationService({ReportType.TYPE_A: TypeATransformationStrategy()},
                                        rules={ReportType.TYPE_A: frozen_times})
        assert service.transform(report).rows == report.rows


class TestRoundTimes:
    """Decision 42: the new times look like the source: round stays round, exact stays exact."""

    def test_round_source_gives_round_times(self, variant):
        # The source has only 8:30 and 12:00; the shift is up to 15 minutes -> quarter hours.
        for row in variant.rows:
            if row.has_hours:
                assert row.entry_minutes % 15 == 0 and row.exit_minutes % 15 == 0
                assert row.total_minutes % 15 == 0  # 3.25 / 3.50 / 3.75 hours

    def test_minute_precise_source_stays_minute_precise(self):
        times = [(481, 665), (483, 663), (484, 657), (481, 659), (482, 663)]  # 8:01-11:05 ...
        rows = tuple(AttendanceRow(row_date=date(2023, 1, day), entry_minutes=entry, exit_minutes=exit_,
                                   total_minutes=exit_ - entry) for day, (entry, exit_) in enumerate(times, 1))
        report = AttendanceReport(ReportType.TYPE_A, ReportHeader(month=date(2023, 1, 1)), rows, ReportSummary())
        new_times = [t for row in make_service().transform(report).rows for t in (row.entry_minutes, row.exit_minutes)]
        assert any(t % 5 for t in new_times)


class TestSummary:
    def test_monthly_total_is_the_sum_of_the_rows(self, variant):
        assert variant.summary.total_minutes == sum(r.total_minutes for r in variant.rows if r.has_hours)

    def test_pay_is_rate_times_hours(self, variant):
        hours = Decimal(variant.summary.total_minutes) / 60
        assert variant.summary.total_pay == (Decimal("30.65") * hours).quantize(Decimal("0.01"))

    def test_working_days_are_recounted(self, variant):
        assert variant.summary.days_count == sum(1 for r in variant.rows if r.has_hours)

    def test_source_days_count_is_not_copied(self, report):
        wrong_count = replace(report, summary=replace(report.summary, days_count=20))
        assert make_service().transform(wrong_count).summary.days_count == 5

    def test_no_rate_means_no_pay_and_a_warning(self, caplog):
        variant = make_service().transform(make_report(hourly_rate=None))
        assert variant.summary.total_pay is None
        assert "hourly rate was not read" in caplog.text


class TestService:
    def test_type_without_strategy_is_a_clear_error(self, report):
        with pytest.raises(TransformationError):
            make_service().transform(replace(report, report_type=ReportType.TYPE_B))

    def test_the_loop_works_with_any_strategy(self, report):
        """The service does not know how a row changes: a fake strategy is enough to test the loop."""

        class KeepEverything(BaseTransformationStrategy):
            def __init__(self) -> None:
                self.rows_seen = 0

            def transform_row(self, row, rules, rng):
                self.rows_seen += 1
                return row

            def build_summary(self, rows, original):
                return original

        fake = KeepEverything()
        result = TransformationService({ReportType.TYPE_A: fake}).transform(report)
        assert result == report
        assert fake.rows_seen == len(report.rows)

    def test_a_strategy_must_implement_both_steps(self):
        class OnlyRows(BaseTransformationStrategy):
            def transform_row(self, row, rules, rng):
                return row

        with pytest.raises(TypeError):
            OnlyRows()


def type_b_row(day: int, kind: RowKind = RowKind.WORK, entry: int = 480, exit_: int = 900) -> AttendanceRow:
    total = exit_ - entry - 30
    buckets = {RowKind.WORK: (total, 0, 0, 0), RowKind.SHABBAT: (0, 0, 0, total),
               RowKind.HOLIDAY: (0, 0, total, 0)}[kind]
    return AttendanceRow(row_date=date(2022, 10, day), kind=kind, entry_minutes=entry, exit_minutes=exit_,
                         total_minutes=total, workplace="גליליון", break_minutes=30,
                         pay_100_minutes=buckets[0], pay_125_minutes=buckets[1],
                         pay_150_minutes=buckets[2], shabbat_minutes=buckets[3])


def make_type_b_report() -> AttendanceReport:
    rows = (type_b_row(2), type_b_row(8, RowKind.SHABBAT), type_b_row(17, RowKind.HOLIDAY), type_b_row(18))
    return AttendanceReport(
        report_type=ReportType.TYPE_B,
        header=ReportHeader(month=date(2022, 10, 1)),
        rows=rows,
        summary=ReportSummary(days_count=4, total_minutes=1560, pay_100_minutes=780, pay_125_minutes=0,
                              pay_150_minutes=390, shabbat_minutes=390, total_break_minutes=120,
                              bonus=Decimal("0"), travel=Decimal("0")),
    )


def make_full_service() -> TransformationService:
    return TransformationService({ReportType.TYPE_A: TypeATransformationStrategy(),
                                  ReportType.TYPE_B: TypeBTransformationStrategy()})


class TestTypeB:
    @pytest.fixture
    def report_b(self) -> AttendanceReport:
        return make_type_b_report()

    @pytest.fixture
    def variant_b(self, report_b) -> AttendanceReport:
        return make_full_service().transform(report_b)

    def test_original_is_not_changed(self, report_b):
        make_full_service().transform(report_b)
        assert report_b == make_type_b_report()

    def test_same_input_same_output(self, report_b):
        assert make_full_service().transform(report_b) == make_full_service().transform(report_b)

    def test_break_stays_as_in_the_source(self, variant_b):
        assert all(row.break_minutes == 30 for row in variant_b.rows)

    def test_total_is_exit_minus_entry_minus_break(self, variant_b):
        for row in variant_b.rows:
            assert row.total_minutes == row.exit_minutes - row.entry_minutes - row.break_minutes

    def test_split_adds_up_to_the_total(self, variant_b):
        for row in variant_b.rows:
            split = row.pay_100_minutes + row.pay_125_minutes + row.pay_150_minutes + row.shabbat_minutes
            assert split == row.total_minutes

    def test_shabbat_hours_stay_in_the_shabbat_column(self, variant_b):
        shabbat = variant_b.rows[1]
        assert shabbat.shabbat_minutes == shabbat.total_minutes and shabbat.pay_100_minutes == 0

    def test_holiday_hours_stay_at_150(self, variant_b):
        holiday = variant_b.rows[2]
        assert holiday.pay_150_minutes == holiday.total_minutes and holiday.pay_100_minutes == 0

    def test_summary_is_computed_again(self, variant_b):
        summary = variant_b.summary
        assert summary.total_minutes == sum(row.total_minutes for row in variant_b.rows)
        assert summary.pay_100_minutes == sum(row.pay_100_minutes for row in variant_b.rows)
        assert summary.shabbat_minutes == sum(row.shabbat_minutes for row in variant_b.rows)
        assert summary.total_break_minutes == 4 * 30
        assert summary.bonus == Decimal("0")  # not computed from the hours: kept

    def test_a_long_day_is_split_into_overtime(self):
        long_day = type_b_row(2, entry=7 * 60, exit_=17 * 60)  # 10 hours - 0:30 break = 9.5 hours
        rules = TransformRules(entry_shift_minutes=0, exit_shift_minutes=0)
        row = TypeBTransformationStrategy().transform_row(long_day, rules, Random(1))
        assert (row.pay_100_minutes, row.pay_125_minutes, row.pay_150_minutes) == (480, 60, 30)

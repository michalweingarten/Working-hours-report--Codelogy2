"""Tests for parsing/type_a_parser.py and parsing/parser_factory.py.

They run on the saved OCR texts in tests/fixtures/ (every n_r_* file is type A).
The OCR differs between machines, so most tests check things that must hold for
EVERY fixture; exact values are checked only on the Linux texts, where they are known.
"""
import calendar
from datetime import date

import pytest

from domain.exceptions import ParsingError
from domain.models import ReportType, RowKind
from parsing.parser_factory import create_parser
from parsing.base_parser import BaseParser
from parsing.type_a_parser import SATURDAY, TypeAParser
from parsing.type_b_parser import TypeBParser
from tests.conftest import FIXTURES_DIR

TYPE_A_FIXTURES = sorted(p.name for p in FIXTURES_DIR.glob("n_r_*.txt"))
TYPE_B_FIXTURES = sorted(p.name for p in FIXTURES_DIR.glob("a_r_*.txt"))
EXPECTED_MONTH = {"n_r_5_n": date(2022, 9, 1), "n_r_10_n": date(2023, 1, 1),
                  "a_r_9": date(2022, 10, 1), "a_r_25": date(2023, 2, 1)}
# The real dates of the rows of each type B source (read from the scans by eye).
REAL_TYPE_B_DAYS = {
    "a_r_9": [2, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 25, 26, 27, 28, 30, 31],
    "a_r_25": [1, 2, 5, 7, 12, 13, 14, 15, 16, 19, 20, 22, 23, 26, 27],
}
EIGHT_THIRTY, NOON = 8 * 60 + 30, 12 * 60


def sample_name(fixture_name: str) -> str:
    return fixture_name.rsplit("_", 1)[0]  # "n_r_5_n_linux.txt" -> "n_r_5_n"


@pytest.fixture
def parse(read_fixture):
    return lambda name: TypeAParser().parse(read_fixture(name))


class TestEveryTypeASample:
    @pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
    def test_month_is_found(self, parse, fixture_name):
        assert parse(fixture_name).header.month == EXPECTED_MONTH[sample_name(fixture_name)]

    @pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
    def test_whole_month_one_row_per_day_in_order(self, parse, fixture_name):
        report = parse(fixture_name)
        month = report.header.month
        days_in_month = calendar.monthrange(month.year, month.month)[1]
        assert [row.row_date.day for row in report.rows] == list(range(1, days_in_month + 1))

    @pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
    def test_saturday_is_shabbat_without_hours(self, parse, fixture_name):
        for row in parse(fixture_name).rows:
            is_saturday = row.row_date.weekday() == SATURDAY
            assert (row.kind is RowKind.SHABBAT) == is_saturday
            if is_saturday:
                assert not row.has_hours

    @pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
    def test_every_row_with_hours_is_logical(self, parse, fixture_name):
        for row in parse(fixture_name).rows:
            if row.has_hours:
                assert row.exit_minutes > row.entry_minutes
                assert row.total_minutes == row.exit_minutes - row.entry_minutes

    @pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
    def test_type_b_fields_stay_empty(self, parse, fixture_name):
        for row in parse(fixture_name).rows:
            assert row.break_minutes is None and row.pay_100_minutes is None

    @pytest.mark.parametrize("fixture_name", TYPE_A_FIXTURES)
    def test_report_type(self, parse, fixture_name):
        assert parse(fixture_name).report_type is ReportType.TYPE_A


class TestKnownValuesOnLinuxTexts:
    def test_n_r_5_n_has_the_24_working_days_of_the_source(self, parse):
        rows = parse("n_r_5_n_linux.txt").rows
        assert sum(row.has_hours for row in rows) == 24

    def test_n_r_5_n_holidays_have_no_hours(self, parse):
        rows = {row.row_date.day: row for row in parse("n_r_5_n_linux.txt").rows}
        assert not rows[26].has_hours and not rows[27].has_hours

    def test_n_r_5_n_windows_line_with_only_a_bar_is_a_lost_row(self, parse):
        # In the Windows OCR, 29/9 is a line with only "|". It is a lost row, not a day off.
        rows = parse("n_r_5_n_windows.txt").rows
        row = next(row for row in rows if row.row_date.day == 29)
        assert row.has_hours
        assert sum(r.has_hours for r in rows) == 24

    def test_n_r_5_n_lost_row_is_rebuilt_from_the_usual_shift(self, parse):
        # 4/9 is not readable at all in the OCR text; Sundays there are 8:30-12:00.
        row = next(row for row in parse("n_r_5_n_linux.txt").rows if row.row_date.day == 4)
        assert (row.entry_minutes, row.exit_minutes) == (EIGHT_THIRTY, NOON)

    def test_n_r_5_n_summary_days(self, parse):
        assert parse("n_r_5_n_linux.txt").summary.days_count == 20

    def test_n_r_10_n_has_the_21_working_days_of_the_source(self, parse):
        rows = parse("n_r_10_n_linux.txt").rows
        assert sum(row.has_hours for row in rows) == 21
        days_off = {row.row_date.day for row in rows if not row.has_hours and row.kind is RowKind.WORK}
        assert days_off == {5, 6, 12, 13, 20, 27}

    def test_n_r_10_n_row_completed_from_one_time_and_the_total(self, parse):
        # OCR read "810 | 303" for 23/1: entry 8:10 and 3.03 hours -> exit 11:12, as in the source.
        row = next(row for row in parse("n_r_10_n_linux.txt").rows if row.row_date.day == 23)
        assert (row.entry_minutes, row.exit_minutes) == (8 * 60 + 10, 11 * 60 + 12)


class TestBadInput:
    def test_no_dates_at_all(self):
        with pytest.raises(ParsingError):
            TypeAParser().parse("nothing here | 8:30 | 12:00")

    def test_dates_but_no_times(self):
        with pytest.raises(ParsingError):
            TypeAParser().parse("| 1/9/22 |\n| 2/9/22 |")


class TestFactory:
    def test_type_a_gets_the_type_a_parser(self):
        assert isinstance(create_parser(ReportType.TYPE_A), TypeAParser)

    def test_type_b_gets_the_type_b_parser(self):
        assert isinstance(create_parser(ReportType.TYPE_B), TypeBParser)


@pytest.fixture
def parse_b(read_fixture):
    return lambda name: TypeBParser().parse(read_fixture(name))


class TestEveryTypeBSample:
    @pytest.mark.parametrize("fixture_name", TYPE_B_FIXTURES)
    def test_month_and_number_of_rows(self, parse_b, fixture_name):
        report = parse_b(fixture_name)
        sample = sample_name(fixture_name)
        assert report.header.month == EXPECTED_MONTH[sample]
        assert len(report.rows) == len(REAL_TYPE_B_DAYS[sample])

    @pytest.mark.parametrize("fixture_name", TYPE_B_FIXTURES)
    def test_dates_increase_and_almost_all_are_right(self, parse_b, fixture_name):
        days = [row.row_date.day for row in parse_b(fixture_name).rows]
        real = REAL_TYPE_B_DAYS[sample_name(fixture_name)]
        assert days == sorted(set(days))
        assert sum(1 for got, want in zip(days, real) if got == want) >= len(real) - 1

    @pytest.mark.parametrize("fixture_name", TYPE_B_FIXTURES)
    def test_every_row_keeps_the_rules(self, parse_b, fixture_name):
        from transformation.validation import row_violations

        for row in parse_b(fixture_name).rows:
            assert row_violations(row) == [], row

    @pytest.mark.parametrize("fixture_name", TYPE_B_FIXTURES)
    def test_break_is_read_by_position_not_as_the_smallest_time(self, parse_b, fixture_name):
        for row in parse_b(fixture_name).rows:
            assert row.break_minutes == 30 and row.entry_minutes >= 8 * 60


class TestTypeBKnownValues:
    def test_all_dates_right_on_the_linux_texts(self, parse_b):
        for sample, real in REAL_TYPE_B_DAYS.items():
            assert [row.row_date.day for row in parse_b(f"{sample}_linux.txt").rows] == real

    def test_a_reversed_line_is_read_in_column_order(self, parse_b):
        # On Windows the OCR wrote every row of a_r_25 left to right:
        # "0.00 0.00 0.00 7.50 7.50 00:30 16:00 08:00 ... 3". Entry is still 08:00, not 00:30.
        report = parse_b("a_r_25_windows.txt")
        first = report.rows[0]
        assert (first.entry_minutes, first.exit_minutes, first.break_minutes) == (480, 960, 30)
        assert first.pay_100_minutes == 450
        assert [row.row_date.day for row in report.rows] == REAL_TYPE_B_DAYS["a_r_25"]
        assert report.summary.days_count == 15 and report.summary.total_minutes == 6630

    def test_shabbat_and_holiday(self, parse_b):
        kinds = {row.row_date.day: row.kind for row in parse_b("a_r_9_linux.txt").rows}
        assert [day for day, kind in kinds.items() if kind is RowKind.SHABBAT] == [8, 15, 22]
        assert [day for day, kind in kinds.items() if kind is RowKind.HOLIDAY] == [17]

    def test_workplace_and_company(self, parse_b):
        report = parse_b("a_r_25_linux.txt")
        assert {row.workplace for row in report.rows} == {"גונן"}
        assert report.header.company_name.endswith('בע"מ')

    def test_summary_under_the_table(self, parse_b):
        summary = parse_b("a_r_9_linux.txt").summary
        assert summary.days_count == 22
        assert summary.total_minutes == 143 * 60
        assert (summary.pay_100_minutes, summary.pay_150_minutes, summary.shabbat_minutes) == (117 * 60, 390, 1170)
        assert parse_b("a_r_25_linux.txt").summary.total_break_minutes == 7 * 60 + 30


class TestBaseParser:
    def test_both_parsers_share_the_parse_flow(self):
        assert TypeAParser.parse is BaseParser.parse and TypeBParser.parse is BaseParser.parse

    def test_a_parser_must_fill_in_both_steps(self):
        class OnlyRows(BaseParser):
            report_type = ReportType.TYPE_A

            def _parse_rows(self, lines):
                return []

        with pytest.raises(TypeError):
            OnlyRows()

    def test_no_rows_is_a_clear_error(self):
        with pytest.raises(ParsingError, match="TYPE_B"):
            TypeBParser().parse("nothing that looks like a row")

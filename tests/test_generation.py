"""Tests for generation/: the HTML page of each report type, and the PDF made from it."""
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from domain.exceptions import GenerationError
from domain.models import AttendanceReport, AttendanceRow, ReportHeader, ReportSummary, ReportType, RowKind
from generation.base_renderer import BaseRenderer
from generation.html_renderer import HtmlRenderer
from generation.layouts import LAYOUTS, Column, PageLayout, Table

GENERATION_DIR = Path(__file__).parent.parent / "generation"


def make_type_a() -> AttendanceReport:
    return AttendanceReport(
        report_type=ReportType.TYPE_A,
        header=ReportHeader(month=date(2022, 9, 1)),
        rows=(
            AttendanceRow(row_date=date(2022, 9, 1), entry_minutes=510, exit_minutes=720, total_minutes=210),
            AttendanceRow(row_date=date(2022, 9, 3), kind=RowKind.SHABBAT),
            AttendanceRow(row_date=date(2022, 9, 26), notes="ראש השנה"),
        ),
        summary=ReportSummary(days_count=24, total_minutes=5040, hourly_rate=Decimal("30.65"),
                              total_pay=Decimal("2574.60")),
    )


def make_type_b() -> AttendanceReport:
    def row(day: int, kind: RowKind, buckets: tuple[int, int, int, int]) -> AttendanceRow:
        pay_100, pay_125, pay_150, shabbat = buckets
        return AttendanceRow(row_date=date(2022, 10, day), kind=kind, entry_minutes=480, exit_minutes=900,
                             total_minutes=390, workplace="גליליון", break_minutes=30, pay_100_minutes=pay_100,
                             pay_125_minutes=pay_125, pay_150_minutes=pay_150, shabbat_minutes=shabbat)

    return AttendanceReport(
        report_type=ReportType.TYPE_B,
        header=ReportHeader(company_name='נ.ע. הנשר כח אדם בע"מ', month=date(2022, 10, 1)),
        rows=(row(2, RowKind.WORK, (390, 0, 0, 0)), row(8, RowKind.SHABBAT, (0, 0, 0, 390)),
              row(17, RowKind.HOLIDAY, (0, 0, 390, 0))),
        summary=ReportSummary(days_count=3, total_minutes=1170, pay_100_minutes=390, pay_125_minutes=0,
                              pay_150_minutes=390, shabbat_minutes=390, total_break_minutes=90,
                              bonus=Decimal("0"), travel=Decimal("0")),
    )


def cells(html: str) -> list[str]:
    return re.findall(r"<td[^>]*>([^<]*)</td>", html)


@pytest.fixture
def html_a() -> str:
    return HtmlRenderer().to_html(make_type_a())


@pytest.fixture
def html_b() -> str:
    return HtmlRenderer().to_html(make_type_b())


class TestHebrewAndDirection:
    @pytest.mark.parametrize("make", [make_type_a, make_type_b])
    def test_right_to_left_hebrew_page(self, make):
        html = HtmlRenderer().to_html(make())
        assert 'dir="rtl"' in html and 'lang="he"' in html and 'charset="utf-8"' in html

    def test_font_has_hebrew_letters(self, html_a):
        # Arial (Windows) and Liberation Sans (Linux / Docker) both have Hebrew.
        assert "Arial" in html_a and "Liberation Sans" in html_a

    def test_numbers_in_boxes_stay_left_to_right(self, html_a):
        assert ".ltr { direction: ltr; }" in html_a


class TestTypeALooksLikeTheSource:
    def test_a4_page_with_no_printer_margins(self, html_a):
        assert "size: A4" in html_a and "width: 210mm" in html_a

    def test_times_without_a_leading_zero(self, html_a):
        assert "8:30" in cells(html_a) and "12:00" in cells(html_a) and "08:30" not in cells(html_a)

    def test_row_values(self, html_a):
        for text in ("1/9/22", "חמישי", "3.50", "ראש השנה"):
            assert text in cells(html_a)

    def test_two_line_column_headers(self, html_a):
        assert "יום<br>בשבוע" in html_a and "שעת<br>כניסה" in html_a

    def test_shabbat_row_is_grey_except_the_notes(self, html_a):
        shabbat_row = next(row for row in html_a.split("<tr") if "3/9/22" in row)
        assert shabbat_row.count('class="shaded"') == 5  # all six columns but the notes

    def test_summary_box(self, html_a):
        for text in ("24", "84.00", "₪ 30.65", "₪ 2,574.60"):
            assert text in cells(html_a)
        assert "ספט-22" in html_a

    def test_values_not_read_from_the_source_stay_empty(self):
        report = make_type_a()
        assert "₪" not in HtmlRenderer().to_html(replace(report, summary=ReportSummary()))


class TestTypeBLooksLikeTheSource:
    def test_company_line(self, html_b):
        assert 'נ.ע. הנשר כח אדם בע&quot;מ' in html_b

    def test_row_values_in_the_source_format(self, html_b):
        row = cells(html_b)[:11]
        assert row == ["02/10/2022", "יום ראשון", "גליליון", "08:00", "15:00", "00:30",
                       "6.50", "6.50", "0.00", "0.00", "0.00"]

    def test_shabbat_row_says_shabbat_and_only_the_day_is_grey(self, html_b):
        shabbat_row = next(row for row in html_b.split("<tr") if "08/10/2022" in row)
        assert ">שבת<" in shabbat_row and shabbat_row.count('class="shaded"') == 1

    def test_totals_row_under_the_table(self, html_b):
        totals = cells(html_b)[33:44]
        assert totals[0] == "3" and totals[5] == "01:30" and totals[6] == "19.50"

    def test_small_summary_box_shows_short_numbers(self, html_b):
        box = cells(html_b)[44:]
        assert box[:4] == ["ימים", "3", "סה&quot;כ שעות", "19.5"]
        assert "בונוס" in box and "0" in box


class TestRenderers:
    def test_html_renderer_writes_a_new_file(self, tmp_path):
        target = HtmlRenderer().render(make_type_a(), tmp_path / "variant.html")
        assert target.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")

    def test_every_format_is_a_renderer(self):
        from generation.pdf_renderer import PdfRenderer

        for renderer in (HtmlRenderer(), PdfRenderer()):
            assert isinstance(renderer, BaseRenderer)
            assert renderer.file_extension.startswith(".")

    def test_every_report_type_has_a_layout(self):
        assert set(LAYOUTS) == set(ReportType)

    def test_type_without_layout_is_a_clear_error(self):
        with pytest.raises(GenerationError):
            HtmlRenderer({ReportType.TYPE_A: LAYOUTS[ReportType.TYPE_A]}).to_html(make_type_b())

    def test_columns_come_from_the_layout(self):
        two_columns = PageLayout(font_size_pt=11, font_weight="bold", blocks=(
            Table(top_mm=10, right_mm=10, header_height_mm=5, row_height_mm=5, style="grid",
                  header_font_size_pt=10, header_bold=True,
                  columns=(Column("תאריך", "date_short", 20), Column("הערות", "notes", 20))),
        ))
        html = HtmlRenderer({ReportType.TYPE_A: two_columns}).to_html(make_type_a())
        assert "שעת יציאה" not in html and "ראש השנה" in html

    def test_renderer_has_no_if_on_the_report_type(self):
        code = (GENERATION_DIR / "html_renderer.py").read_text(encoding="utf-8")
        assert "ReportType.TYPE_" not in code


def test_generation_does_not_import_other_stations():
    for source in GENERATION_DIR.glob("*.py"):
        code = source.read_text(encoding="utf-8")
        for forbidden in ("from parsing", "import parsing", "from transformation", "pytesseract"):
            assert forbidden not in code, f"{source.name} uses {forbidden}"


@pytest.mark.parametrize("make", [make_type_a, make_type_b])
def test_pdf_is_made(tmp_path, make):
    """Needs Playwright and a browser; skipped (not failed) where they are missing."""
    pytest.importorskip("playwright")
    from generation.pdf_renderer import PdfRenderer

    target = tmp_path / "variant.pdf"
    try:
        PdfRenderer().render(make(), target)
    except GenerationError as error:
        pytest.skip(f"No browser to print with: {error}")
    assert target.read_bytes().startswith(b"%PDF")
    from pdf2image import pdfinfo_from_path
    assert pdfinfo_from_path(str(target))["Pages"] == 1  # the whole month fits on one A4 page


class TestPdfBrowserChoice:
    """Which browser prints the PDF. Fakes stand in for Playwright, so no browser is needed."""

    class FakeError(Exception):
        pass

    def make_playwright(self, working_channels):
        error = self.FakeError

        class FakeChromium:
            def __init__(self):
                self.tried = []

            def launch(self, channel=None):
                self.tried.append(channel)
                if channel not in working_channels:
                    raise error(f"Executable doesn't exist for {channel}\nmore details")
                return f"browser:{channel}"

        class FakePlaywright:
            chromium = FakeChromium()

        return FakePlaywright()

    def test_falls_back_to_an_installed_browser(self):
        from generation.pdf_renderer import PdfRenderer

        playwright = self.make_playwright(working_channels={"msedge"})
        renderer = PdfRenderer(browser_channels=(None, "msedge", "chrome"))
        assert renderer._launch_browser(playwright, self.FakeError) == "browser:msedge"
        assert playwright.chromium.tried == [None, "msedge"]

    def test_no_browser_at_all_is_one_clear_error(self):
        from generation.pdf_renderer import PdfRenderer

        renderer = PdfRenderer(browser_channels=(None, "msedge"))
        with pytest.raises(GenerationError) as caught:
            renderer._launch_browser(self.make_playwright(working_channels=set()), self.FakeError)
        message = str(caught.value)
        assert "Playwright Chromium" in message and "msedge" in message and "more details" not in message

"""Where everything sits on the page, per report type. Measured on the scanned sources.

All sizes are in millimetres on an A4 page (210 x 297), measured on the scans at
300 DPI: type A on n_r_5_n.pdf (checked on n_r_10_n.pdf), type B on a_r_9.pdf
(checked on a_r_25.pdf).

The difference between report types is DATA here, not an if in the renderer:
a layout is a list of blocks (a box, a table, a line of text...), and LAYOUTS maps each
report type to its layout. Which value goes in a table column is named by its `field`,
a key of the formatters in html_renderer.py. A new report type = a new entry in LAYOUTS.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from domain.models import ReportType

FONT_FAMILY: Final[str] = 'Arial, "Liberation Sans", "DejaVu Sans", sans-serif'


@dataclass(frozen=True)
class Column:
    title: str  # "\n" splits a two-line header, as in the source
    field: str  # which value goes in the column: a key of CELL_FORMATTERS
    width_mm: float
    shaded_on_shabbat: bool = False  # grey in a Shabbat row
    align: str = "center"
    header_shaded: bool = False


@dataclass(frozen=True)
class NameBox:
    """Type A: 'employee name' and an empty row, above the totals box."""

    top_mm: float
    right_mm: float  # distance from the right edge of the page
    label_width_mm: float
    value_width_mm: float
    row_height_mm: float
    blank_row_height_mm: float


@dataclass(frozen=True)
class LabelValueBox:
    """A box of 'label | value' rows. Each value is a key of SUMMARY_FORMATTERS."""

    right_mm: float
    label_width_mm: float
    value_width_mm: float
    row_height_mm: float
    rows: tuple[tuple[str, str], ...]  # (label, summary field)
    top_mm: float | None = None  # None: right under the table above it
    value_align: str = "center"
    label_align: str = "center"
    font_size_pt: float | None = None
    font_weight: str | None = None


@dataclass(frozen=True)
class MonthBar:
    """Type A: the grey 'employee card for month: Sep-22' bar."""

    top_mm: float
    right_mm: float
    label_width_mm: float
    value_width_mm: float
    gap_mm: float
    height_mm: float


@dataclass(frozen=True)
class CompanyLine:
    """Type B: the name of the company above the table."""

    top_mm: float
    right_mm: float
    font_size_pt: float


@dataclass(frozen=True)
class Table:
    top_mm: float
    right_mm: float
    header_height_mm: float
    row_height_mm: float
    columns: tuple[Column, ...]
    style: str  # "grid": every cell has borders (type A); "plain": only the header is framed (type B)
    header_font_size_pt: float
    header_bold: bool
    totals_row: bool = False  # type B: a row of totals right under the rows


Block = NameBox | LabelValueBox | MonthBar | CompanyLine | Table


@dataclass(frozen=True)
class PageLayout:
    blocks: tuple[Block, ...]
    font_size_pt: float
    font_weight: str


TYPE_A_LAYOUT: Final[PageLayout] = PageLayout(
    font_size_pt=11.0,
    font_weight="bold",
    blocks=(
        NameBox(top_mm=34.0, right_mm=38.0, label_width_mm=20.0, value_width_mm=38.5,
                row_height_mm=5.0, blank_row_height_mm=4.0),
        LabelValueBox(
            top_mm=43.0, right_mm=20.3, label_width_mm=53.6, value_width_mm=22.3, row_height_mm=4.8,
            rows=(('סה"כ ימי עבודה לחודש', "days"), ('סה"כ שעות חודשיות', "hours"),
                  ("מחיר לשעה", "hourly_rate"), ('סה"כ לתשלום', "total_pay")),
        ),
        MonthBar(top_mm=66.6, right_mm=38.0, label_width_mm=37.0, value_width_mm=36.5,
                 gap_mm=2.5, height_mm=5.0),
        Table(
            top_mm=76.2, right_mm=20.2, header_height_mm=9.5, row_height_mm=4.53, style="grid",
            header_font_size_pt=10.5, header_bold=True,
            columns=(
                Column("תאריך", "date_short", 17.6, shaded_on_shabbat=True),
                Column("יום\nבשבוע", "weekday", 18.1, shaded_on_shabbat=True),
                Column("שעת\nכניסה", "entry", 17.9, shaded_on_shabbat=True),
                Column("שעת יציאה", "exit", 22.0, shaded_on_shabbat=True),
                Column('סה"כ\nשעות', "total", 18.0, shaded_on_shabbat=True),
                Column("הערות", "notes", 18.0),
            ),
        ),
    ),
)

TYPE_B_LAYOUT: Final[PageLayout] = PageLayout(
    font_size_pt=11.0,
    font_weight="normal",
    blocks=(
        CompanyLine(top_mm=27.3, right_mm=24.5, font_size_pt=12.0),
        Table(
            top_mm=36.5, right_mm=22.3, header_height_mm=4.6, row_height_mm=4.55, style="plain",
            header_font_size_pt=11.0, header_bold=True, totals_row=True,
            columns=(
                Column("תאריך", "date_full", 21.2, align="right"),
                Column("יום", "weekday_full", 18.5, align="right", shaded_on_shabbat=True, header_shaded=True),
                Column("מקום ע.", "workplace", 13.5, align="right"),
                Column("כניסה", "entry_padded", 12.0, align="right"),
                Column("יציאה", "exit_padded", 11.2, align="right"),
                Column("הפסקה", "break", 14.6, align="right"),
                Column('סה"כ', "total", 13.0, align="right"),
                Column("100%", "pay_100", 13.3, align="right"),
                Column("125%", "pay_125", 13.3, align="right"),
                Column("150%", "pay_150", 13.4, align="right"),
                Column("שבת", "shabbat", 11.5, align="right"),
            ),
        ),
        LabelValueBox(
            right_mm=23.0, label_width_mm=20.9, value_width_mm=18.4, row_height_mm=4.55,
            value_align="right", label_align="right", font_size_pt=10.5, font_weight="normal",
            rows=(("ימים", "days"), ('סה"כ שעות', "hours_short"), ("שעות 100%", "pay_100_short"),
                  ("שעות 125%", "pay_125_short"), ("שעות 150%", "pay_150_short"),
                  ("שבת 150%", "shabbat_short"), ("בונוס", "bonus"), ("נסיעות", "travel")),
        ),
    ),
)

LAYOUTS: Final[Mapping[ReportType, PageLayout]] = {
    ReportType.TYPE_A: TYPE_A_LAYOUT,
    ReportType.TYPE_B: TYPE_B_LAYOUT,
}

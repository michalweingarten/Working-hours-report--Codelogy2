"""Station 5: AttendanceReport -> HTML page that looks like the scanned source.

It knows only AttendanceReport and the page layout: nothing about OCR, parsing or the
change rules, and it computes nothing: every number is already in the report.
The page is an A4 sheet with every block placed in millimetres (layouts.py), right to
left, in a font that has Hebrew letters. pdf_renderer.py prints the same HTML.

There is no if on the report type here. The layout of the type is a list of blocks;
each kind of block has one render function (BLOCK_RENDERERS), and what goes in each
column or box row is looked up by name (CELL_FORMATTERS, SUMMARY_FORMATTERS, TOTALS_FORMATTERS).
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Final

from config.rules import TEXT_FILE_ENCODING
from domain.exceptions import GenerationError
from domain.models import AttendanceReport, AttendanceRow, ReportSummary, RowKind
from domain.time_math import MINUTES_PER_HOUR, minutes_to_decimal_hours
from generation.base_renderer import BaseRenderer
from generation.layouts import (
    FONT_FAMILY,
    LAYOUTS,
    Block,
    CompanyLine,
    LabelValueBox,
    MonthBar,
    NameBox,
    PageLayout,
    Table,
)

# Display facts, by date.weekday() (Monday = 0) and by month number.
HEBREW_DAY_NAMES: Final[tuple[str, ...]] = ("שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון")
HEBREW_MONTH_SHORT: Final[tuple[str, ...]] = (
    "ינו", "פבר", "מרץ", "אפר", "מאי", "יונ", "יול", "אוג", "ספט", "אוק", "נוב", "דצמ",
)
SATURDAY: Final[int] = 5
SHEKEL: Final[str] = "₪"
SHADE: Final[str] = "#c9c9c9"  # the grey of Shabbat rows and label cells
LINE: Final[str] = "0.35mm solid #000"


@dataclass
class _Page:
    """What the blocks drawn so far left behind: where the last table ended."""

    report: AttendanceReport
    last_table_bottom_mm: float = 0.0


class HtmlRenderer(BaseRenderer):
    file_extension = ".html"

    def __init__(self, layouts: Mapping = LAYOUTS) -> None:
        self._layouts = layouts

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        output_path.write_text(self.to_html(report), encoding=TEXT_FILE_ENCODING)
        return output_path

    def to_html(self, report: AttendanceReport) -> str:
        layout: PageLayout | None = self._layouts.get(report.report_type)
        if layout is None:
            raise GenerationError(f"There is no page layout for {report.report_type.name} yet")
        page = _Page(report)
        blocks = "\n".join(BLOCK_RENDERERS[type(block)](block, page) for block in layout.blocks)
        return "\n".join([
            "<!DOCTYPE html>",
            '<html lang="he" dir="rtl">',
            '<head><meta charset="utf-8"><title>דו"ח נוכחות</title>',
            f"<style>{_style(layout)}</style></head>",
            f'<body><div class="page">\n{blocks}\n</div></body></html>',
        ])


# --- one render function per kind of block -----------------------------------
def _name_box(box: NameBox, page: _Page) -> str:
    return (
        f'<table style="top:{box.top_mm}mm; right:{box.right_mm}mm; '
        f'width:{box.label_width_mm + box.value_width_mm}mm">'
        f'<tr style="height:{box.row_height_mm}mm">'
        f'<td class="shaded" style="width:{box.label_width_mm}mm; text-align:right">שם העובד:</td>'
        f'<td style="width:{box.value_width_mm}mm">{_text(page.report.header.employee_name)}</td></tr>'
        f'<tr style="height:{box.blank_row_height_mm}mm"><td colspan="2"></td></tr>'
        "</table>"
    )


def _label_value_box(box: LabelValueBox, page: _Page) -> str:
    top = box.top_mm if box.top_mm is not None else page.last_table_bottom_mm
    font = ""
    if box.font_size_pt:
        font += f" font-size:{box.font_size_pt}pt;"
    if box.font_weight:
        font += f" font-weight:{box.font_weight};"
    rows = "".join(
        f'<tr style="height:{box.row_height_mm}mm">'
        f'<td style="width:{box.label_width_mm}mm; text-align:{box.label_align}">{escape(label)}</td>'
        f'<td class="ltr" style="width:{box.value_width_mm}mm; text-align:{box.value_align}">'
        f"{escape(SUMMARY_FORMATTERS[field](page.report))}</td></tr>"
        for label, field in box.rows
    )
    width = box.label_width_mm + box.value_width_mm
    return f'<table style="top:{top}mm; right:{box.right_mm}mm; width:{width}mm;{font}">{rows}</table>'


def _month_bar(bar: MonthBar, page: _Page) -> str:
    month = page.report.header.month
    label = f"{HEBREW_MONTH_SHORT[month.month - 1]}-{month:%y}" if month else ""
    return (
        f'<div class="month" style="top:{bar.top_mm}mm; right:{bar.right_mm}mm; '
        f'gap:{bar.gap_mm}mm; height:{bar.height_mm}mm">'
        f'<div style="width:{bar.label_width_mm}mm">כרטיס עובד לחודש:</div>'
        f'<div style="width:{bar.value_width_mm}mm">{escape(label)}</div>'
        "</div>"
    )


def _company_line(line: CompanyLine, page: _Page) -> str:
    return (
        f'<div class="line" style="top:{line.top_mm}mm; right:{line.right_mm}mm; '
        f'font-size:{line.font_size_pt}pt">{_text(page.report.header.company_name)}</div>'
    )


def _table(table: Table, page: _Page) -> str:
    widths = "".join(f'<col style="width:{c.width_mm}mm">' for c in table.columns)
    weight = "bold" if table.header_bold else "normal"
    header = "".join(
        f'<th class="{"shaded" if c.header_shaded else ""}" style="font-size:{table.header_font_size_pt}pt; '
        f'font-weight:{weight}">{"<br>".join(escape(part) for part in c.title.split(chr(10)))}</th>'
        for c in table.columns
    )
    body = "".join(_table_row(table, row) for row in page.report.rows)
    rows_count = len(page.report.rows)
    if table.totals_row:
        body += _totals_row(table, page.report.summary)
        rows_count += 1
    page.last_table_bottom_mm = table.top_mm + table.header_height_mm + rows_count * table.row_height_mm
    width = sum(c.width_mm for c in table.columns)
    return (
        f'<table class="{table.style}" style="top:{table.top_mm}mm; right:{table.right_mm}mm; width:{width}mm">'
        f'<colgroup>{widths}</colgroup>'
        f'<tr style="height:{table.header_height_mm}mm">{header}</tr>{body}</table>'
    ).replace("<tr>", f'<tr style="height:{table.row_height_mm}mm">')


def _table_row(table: Table, row: AttendanceRow) -> str:
    shabbat = row.kind is RowKind.SHABBAT
    cells = "".join(
        f'<td class="{"shaded" if shabbat and c.shaded_on_shabbat else ""}" style="text-align:{c.align}">'
        f"{escape(CELL_FORMATTERS[c.field](row))}</td>"
        for c in table.columns
    )
    return f"<tr>{cells}</tr>"


def _totals_row(table: Table, summary: ReportSummary) -> str:
    cells = "".join(
        f'<td style="text-align:{c.align}">{escape(TOTALS_FORMATTERS.get(c.field, _empty)(summary))}</td>'
        for c in table.columns
    )
    return f"<tr>{cells}</tr>"


BLOCK_RENDERERS: Final[Mapping[type[Block], Callable[[Block, _Page], str]]] = {
    NameBox: _name_box,
    LabelValueBox: _label_value_box,
    MonthBar: _month_bar,
    CompanyLine: _company_line,
    Table: _table,
}


# --- how each value is shown ------------------------------------------------
def _clock(minutes: int | None, two_digit_hour: bool = False) -> str:
    """8:30 (type A) or 08:30 (type B), as in the sources."""
    if minutes is None:
        return ""
    hours, rest = divmod(minutes, MINUTES_PER_HOUR)
    return f"{hours:02d}:{rest:02d}" if two_digit_hour else f"{hours}:{rest:02d}"


def _hours(minutes: int | None) -> str:
    """3.50"""
    return "" if minutes is None else str(minutes_to_decimal_hours(minutes))


def _hours_short(minutes: int | None) -> str:
    """143 / 6.5 / 0: how the small box under the type B table shows hours."""
    if minutes is None:
        return ""
    return _short(minutes_to_decimal_hours(minutes))


def _short(number: Decimal | None) -> str:
    if number is None:
        return ""
    text = f"{number:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _text(value: object | None) -> str:
    return "" if value is None else escape(str(value))


def _money(amount: Decimal | None) -> str:
    return "" if amount is None else f"{SHEKEL} {amount:,.2f}"


def _weekday_full(row: AttendanceRow) -> str:
    """'יום ראשון', and just 'שבת' on Saturday, as in type B."""
    name = HEBREW_DAY_NAMES[row.row_date.weekday()]
    return name if row.row_date.weekday() == SATURDAY else f"יום {name}"


def _empty(_value: object) -> str:
    return ""


CELL_FORMATTERS: Final[Mapping[str, Callable[[AttendanceRow], str]]] = {
    "date_short": lambda row: f"{row.row_date.day}/{row.row_date.month}/{row.row_date:%y}",
    "date_full": lambda row: f"{row.row_date:%d/%m/%Y}",
    "weekday": lambda row: HEBREW_DAY_NAMES[row.row_date.weekday()],
    "weekday_full": _weekday_full,
    "workplace": lambda row: row.workplace or "",
    "entry": lambda row: _clock(row.entry_minutes),
    "exit": lambda row: _clock(row.exit_minutes),
    "entry_padded": lambda row: _clock(row.entry_minutes, two_digit_hour=True),
    "exit_padded": lambda row: _clock(row.exit_minutes, two_digit_hour=True),
    "break": lambda row: _clock(row.break_minutes, two_digit_hour=True),
    "total": lambda row: _hours(row.total_minutes) if row.has_hours else "",
    "pay_100": lambda row: _hours(row.pay_100_minutes),
    "pay_125": lambda row: _hours(row.pay_125_minutes),
    "pay_150": lambda row: _hours(row.pay_150_minutes),
    "shabbat": lambda row: _hours(row.shabbat_minutes),
    "notes": lambda row: row.notes,
}

SUMMARY_FORMATTERS: Final[Mapping[str, Callable[[AttendanceReport], str]]] = {
    "days": lambda report: _text(report.summary.days_count),
    "hours": lambda report: _hours(report.summary.total_minutes),
    "hourly_rate": lambda report: _money(report.summary.hourly_rate),
    "total_pay": lambda report: _money(report.summary.total_pay),
    "hours_short": lambda report: _hours_short(report.summary.total_minutes),
    "pay_100_short": lambda report: _hours_short(report.summary.pay_100_minutes),
    "pay_125_short": lambda report: _hours_short(report.summary.pay_125_minutes),
    "pay_150_short": lambda report: _hours_short(report.summary.pay_150_minutes),
    "shabbat_short": lambda report: _hours_short(report.summary.shabbat_minutes),
    "bonus": lambda report: _short(report.summary.bonus),
    "travel": lambda report: _short(report.summary.travel),
}

# The totals row under the type B table: which summary value goes under which column.
TOTALS_FORMATTERS: Final[Mapping[str, Callable[[ReportSummary], str]]] = {
    "date_full": lambda summary: _text(summary.days_count),
    "break": lambda summary: _clock(summary.total_break_minutes, two_digit_hour=True),
    "total": lambda summary: _hours(summary.total_minutes),
    "pay_100": lambda summary: _hours(summary.pay_100_minutes),
    "pay_125": lambda summary: _hours(summary.pay_125_minutes),
    "pay_150": lambda summary: _hours(summary.pay_150_minutes),
    "shabbat": lambda summary: _hours(summary.shabbat_minutes),
}


# --- style ---------------------------------------------------------------------
def _style(layout: PageLayout) -> str:
    return f"""
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #f0f0f0; }}
.page {{
  position: relative; width: 210mm; height: 297mm; margin: 0 auto; background: #fff;
  font-family: {FONT_FAMILY}; font-size: {layout.font_size_pt}pt; font-weight: {layout.font_weight}; color: #000;
}}
@media print {{ html, body {{ background: #fff; }} }}
table {{ position: absolute; border-collapse: collapse; table-layout: fixed; }}
td, th {{ border: {LINE}; padding: 0 1mm; text-align: center; white-space: nowrap; overflow: hidden; line-height: 1; }}
.shaded {{ background: {SHADE}; }}
.ltr {{ direction: ltr; }}
.grid th {{ vertical-align: bottom; padding-bottom: 0.5mm; }}
.plain td {{ border: none; }}
.plain th {{ border-top: {LINE}; border-bottom: none; border-left: {LINE}; border-right: none; }}
.plain th:last-child {{ border-right: {LINE}; }}
.month {{ position: absolute; display: flex; }}
.month div {{ background: {SHADE}; border: 0.5mm solid #000; display: flex; white-space: nowrap;
  align-items: center; justify-content: center; }}
.line {{ position: absolute; font-weight: bold; white-space: nowrap; }}
"""

"""Which parser reads which report type. The only place that knows the parser classes.

Adding a report type = writing its parser and adding one line to PARSERS.
"""
from collections.abc import Callable, Mapping
from typing import Final, Protocol

from domain.exceptions import ParsingError
from domain.models import AttendanceReport, ReportType
from parsing.type_a_parser import TypeAParser
from parsing.type_b_parser import TypeBParser


class ReportParser(Protocol):
    def parse(self, raw_text: str) -> AttendanceReport: ...


PARSERS: Final[Mapping[ReportType, Callable[[], ReportParser]]] = {
    ReportType.TYPE_A: TypeAParser,
    ReportType.TYPE_B: TypeBParser,
}


def create_parser(report_type: ReportType) -> ReportParser:
    try:
        return PARSERS[report_type]()
    except KeyError:
        raise ParsingError(f"There is no parser for {report_type.name} yet") from None

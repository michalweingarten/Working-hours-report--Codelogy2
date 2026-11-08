"""One error class per station, all sharing a common root.

Catching AttendanceReportError means "anything that went wrong in our pipeline".
Catching a specific subclass means "this exact station failed".
"""


class AttendanceReportError(Exception):
    """Base class for every error raised by this program."""


class OcrError(AttendanceReportError):
    """Station 1 failed: the PDF could not be turned into text."""


class TimeConversionError(AttendanceReportError):
    """A time or an amount of hours could not be converted."""


class ClassificationError(AttendanceReportError):
    """Station 2 failed: the text does not clearly belong to one report type."""


class ParsingError(AttendanceReportError):
    """Station 3 failed: the text could not be turned into a report."""


class TransformationError(AttendanceReportError):
    """Station 4 failed: the report could not be changed."""


class ValidationError(AttendanceReportError):
    """A report breaks one or more rules of a logical report. Lists ALL broken rules."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = list(violations)
        lines = "\n".join(f"  - {violation}" for violation in self.violations)
        super().__init__(f"The report breaks {len(self.violations)} rule(s):\n{lines}")


class GenerationError(AttendanceReportError):
    """Station 5 failed: the output file could not be created."""

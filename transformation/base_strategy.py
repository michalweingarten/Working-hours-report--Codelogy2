"""What every report type must know to be changed: one row, and the summary.

The loop over the rows, the random generator of each row and the final check are
written once, in service.py. A strategy fills in only what differs between types.
"""
from abc import ABC, abstractmethod
from random import Random

from config.rules import TransformRules
from domain.models import AttendanceRow, ReportSummary
from domain.time_math import times_on_grid


class BaseTransformationStrategy(ABC):
    @abstractmethod
    def transform_row(self, row: AttendanceRow, rules: TransformRules, rng: Random) -> AttendanceRow:
        """A new row with moved times and everything computed from them. Days without hours stay as they are."""

    @abstractmethod
    def build_summary(self, rows: tuple[AttendanceRow, ...], original: ReportSummary) -> ReportSummary:
        """The summary computed again from the new rows."""

    @staticmethod
    def _move(minutes: int, max_shift: int, step: int, rng: Random) -> int:
        """A new time within max_shift of the old one, on the grid of the source (decision 42)."""
        if max_shift == 0:
            return minutes
        return rng.choice(times_on_grid(minutes, max_shift, step) or [minutes])

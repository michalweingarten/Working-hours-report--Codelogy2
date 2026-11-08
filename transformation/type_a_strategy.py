"""Station 4 for report type A: move the entry and exit of every working day.

Entry and exit move by DIFFERENT random amounts, so the hours change too. The new
times stay on the "grid" of the source (rules.time_step_minutes): round source times
stay round, minute-precise ones stay minute-precise. Everything computed from them is computed again: the row total, the monthly
total, the number of working days, and the pay (when the hourly rate is known).
A move that would break a row rule is not used; the row stays as in the original.
"""
import logging
from dataclasses import replace
from random import Random

from config.rules import TransformRules
from domain.models import AttendanceRow, ReportSummary
from domain.time_math import worked_minutes
from transformation.base_strategy import BaseTransformationStrategy
from transformation.validation import expected_pay, row_violations

logger = logging.getLogger(__name__)


class TypeATransformationStrategy(BaseTransformationStrategy):
    def transform_row(self, row: AttendanceRow, rules: TransformRules, rng: Random) -> AttendanceRow:
        if not row.has_hours:
            return row  # Shabbat / holiday / day off: no hours are invented
        step = rules.time_step_minutes
        entry = self._move(row.entry_minutes, rules.entry_shift_minutes, step, rng)
        exit_ = self._move(row.exit_minutes, rules.exit_shift_minutes, step, rng)
        moved = replace(row, entry_minutes=entry, exit_minutes=exit_,
                        total_minutes=worked_minutes(entry, exit_, row.break_minutes))
        return row if row_violations(moved) else moved

    def build_summary(self, rows: tuple[AttendanceRow, ...], original: ReportSummary) -> ReportSummary:
        worked = [row for row in rows if row.has_hours]
        total_minutes = sum(row.total_minutes for row in worked)
        rate = original.hourly_rate
        if rate is None:
            logger.warning("the hourly rate was not read, so the total pay is left empty")
        return replace(
            original,
            total_minutes=total_minutes,
            days_count=len(worked),  # decision 29: recounted, not copied from the source
            total_pay=expected_pay(total_minutes, rate) if rate is not None else None,
        )

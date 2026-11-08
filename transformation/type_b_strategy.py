"""Station 4 for report type B: move entry and exit, keep the break, split the hours again.

* Entry and exit move like in type A, on the grid of the source.
* The break stays as in the source (decision 44): TransformRules.break_shift_minutes = 0.
* Shabbat and holiday rows have hours in type B, so they move too, and all their hours
  stay in the Shabbat / 150% column, as in the source (decision 45).
* The row is split again into 100% / 125% / 150% / Shabbat (validation.expected_buckets),
  and the summary under the table is computed again from the new rows.
"""
from dataclasses import replace
from random import Random

from config.rules import TransformRules
from domain.models import AttendanceRow, ReportSummary
from domain.time_math import worked_minutes
from transformation.base_strategy import BaseTransformationStrategy
from transformation.validation import expected_buckets, row_violations


class TypeBTransformationStrategy(BaseTransformationStrategy):
    def transform_row(self, row: AttendanceRow, rules: TransformRules, rng: Random) -> AttendanceRow:
        if not row.has_hours:
            return row
        step = rules.time_step_minutes
        entry = self._move(row.entry_minutes, rules.entry_shift_minutes, step, rng)
        exit_ = self._move(row.exit_minutes, rules.exit_shift_minutes, step, rng)
        break_ = self._move(row.break_minutes or 0, rules.break_shift_minutes, step, rng)
        total = worked_minutes(entry, exit_, break_)
        pay_100, pay_125, pay_150, shabbat = expected_buckets(row.kind, total)
        moved = replace(
            row, entry_minutes=entry, exit_minutes=exit_, break_minutes=break_, total_minutes=total,
            pay_100_minutes=pay_100, pay_125_minutes=pay_125, pay_150_minutes=pay_150, shabbat_minutes=shabbat,
        )
        return row if row_violations(moved) else moved

    def build_summary(self, rows: tuple[AttendanceRow, ...], original: ReportSummary) -> ReportSummary:
        worked = [row for row in rows if row.has_hours]

        def total_of(field: str) -> int:
            return sum(getattr(row, field) or 0 for row in worked)

        return replace(
            original,  # bonus and travel are not computed from the hours: they stay as they are
            days_count=len(worked),
            total_minutes=total_of("total_minutes"),
            pay_100_minutes=total_of("pay_100_minutes"),
            pay_125_minutes=total_of("pay_125_minutes"),
            pay_150_minutes=total_of("pay_150_minutes"),
            shabbat_minutes=total_of("shabbat_minutes"),
            total_break_minutes=total_of("break_minutes"),
        )

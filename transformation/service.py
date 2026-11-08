"""Station 4: report -> NEW report. The original report is never changed.

The service runs the same loop for every report type: it picks the strategy and the
rules of the type from dictionaries (no if on the type), finds how round the times
of the source are, gives every row its own random generator, and checks the new
report against all the rules before it leaves.

The strategies are handed in from outside (main.py builds them), so a test can
hand in a fake one and check only the loop.
"""
from collections.abc import Mapping
from dataclasses import replace
from random import Random

from config.rules import (
    ROUND_TIMES_SHARE,
    TIME_STEP_CANDIDATES,
    TRANSFORM_RULES,
    VARIATION_SEED,
    TransformRules,
)
from domain.exceptions import TransformationError
from domain.models import AttendanceReport, AttendanceRow, ReportType
from domain.time_math import common_time_step
from transformation.base_strategy import BaseTransformationStrategy
from transformation.validation import ensure_valid_variant


class TransformationService:
    def __init__(
        self,
        strategies: Mapping[ReportType, BaseTransformationStrategy],
        rules: Mapping[ReportType, TransformRules] = TRANSFORM_RULES,
        seed: int = VARIATION_SEED,
    ) -> None:
        self._strategies = strategies
        self._rules = rules
        self._seed = seed

    def transform(self, report: AttendanceReport) -> AttendanceReport:
        strategy = self._strategies.get(report.report_type)
        rules = self._rules.get(report.report_type)
        if strategy is None or rules is None:
            raise TransformationError(f"There are no change rules for {report.report_type.name} yet")

        rules = replace(rules, time_step_minutes=self._time_step_of(report, rules))
        rows = tuple(strategy.transform_row(row, rules, self._rng_for(row)) for row in report.rows)
        variant = replace(report, rows=rows, summary=strategy.build_summary(rows, report.summary))
        ensure_valid_variant(report, variant)
        return variant

    @staticmethod
    def _time_step_of(report: AttendanceReport, rules: TransformRules) -> int:
        """How round the times of the source are, so the new times look the same (decision 42)."""
        times = [t for row in report.rows if row.has_hours for t in (row.entry_minutes, row.exit_minutes)]
        largest_allowed = min(rules.entry_shift_minutes, rules.exit_shift_minutes)
        candidates = tuple(step for step in TIME_STEP_CANDIDATES if step <= largest_allowed) or (1,)
        return common_time_step(times, candidates, ROUND_TIMES_SHARE)

    def _rng_for(self, row: AttendanceRow) -> Random:
        """Every row gets its own generator, seeded by (seed, date).

        Same date -> same numbers in every run, and adding or removing a row does not
        change the other rows. A string seed is hashed with SHA-512 by random.Random,
        so unlike hash() it is the same in every run of Python.
        """
        return Random(f"{self._seed}:{row.row_date.isoformat()}")
